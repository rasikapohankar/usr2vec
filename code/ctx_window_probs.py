import argparse
import gensim
from ipdb import set_trace
import os
import sqlite3
import sys
import time

PAD_TOKEN = u'_pad_'
def __create_sql(path, window_size):
    """
        create a sqlite table to store word pairs and scores
        path: path to the DB
    """    
    db = sqlite3.connect(path)
    cursor = db.cursor()
    cursor.execute("CREATE TABLE users(word_pair TEXT PRIMARY KEY, score REAL)")
    #insert the window size as DB record
    cursor.execute("INSERT INTO users(word_pair, score) VALUES (?,?)",("WINDOW_SIZE",window_size))
    db.commit()
    db.close()

def __insert_wordpair(cursor, word_pairs):    
    """
        inserts a set of word pairs into the DB
        cursor: a sqlite cursor
        word_pairs: a list of word pairs (each pair is also list)
    """
    insert_record = "INSERT INTO users(word_pair) VALUES (?)"
    for wp in word_pairs:
        try:               
            cursor.execute(insert_record, (' '.join(wp),))
        except sqlite3.IntegrityError:
            #tried to insert the same key twice, this is fine
            pass
        except Exception as e:
            print "Erro"
            print ' '.join(wp)
            set_trace()
            raise e
            
        

def __update_scores(cursor, word_pairs, scores):    
    """
        updates a set of word pairs with the scores
        cursor: a sqlite cursor
        word_pairs: a list of word pairs (each pair is also list)
        scores: a list of scores
    """
    cmd = "UPDATE users SET score = ? WHERE word_pair = ?"
    for wp, score in zip(word_pairs, scores):                
        cursor.execute(cmd,(score, ' '.join(wp)))        

def extract_windows(tokens, window_size): 
    """
        Given a sentence of tokens = {w1, ..., wn} computes all windows of size n
        the message is padded to ensure that all windows are equal
    """
    padd = [PAD_TOKEN] * window_size
    padded_m = padd + tokens + padd     
    windows = []    
    for i in xrange(len(tokens)):        
        #left window
        wl = padded_m[i:i+window_size]
        #right window
        wr = padded_m[i+window_size+1:(i+1)+window_size*2]
        context_window = wl + wr
        center_word = padded_m[i+window_size]           
        #don't repeat computations for the same pair of words
        word_pairs =  [ [center_word,ctx_word] for 
                        ctx_word in set(context_window) ]                          
        windows.append(word_pairs)
    #flaten the list of windows     
    return [val for sublist in windows for val in sublist]            

class ContextProbabilities:
    def __init__(self, db_path):
        self.db = sqlite3.connect(db_path)
        self.select_cursor = self.db.cursor()
        self.update_cursor = None
        query_window_size = " SELECT score FROM users WHERE word_pair = 'WINDOW_SIZE'"
        self.select_cursor.execute(query_window_size)        
        self.window_size = int(self.select_cursor.fetchone()[0])

    def score_context_windows(self, tokens):
        windows = extract_windows(tokens, self.window_size)                
        keys = tuple(set([' '.join(w) for w in windows]))        
        query= 'SELECT score FROM users WHERE word_pair in (%s)' % ','.join('?'*len(keys))        
        try:
            self.select_cursor.execute(query, keys)
        except Exception as e:
            print "Error with the expression below:\n"
            print keys
            print "sentence: ", ' '.join(tokens)
            raise e
        scores = [x[0] if x[0] is not None else 0 for x in self.select_cursor.fetchall()]        
        return scores

def get_parser():
    parser = argparse.ArgumentParser(description="Compute context log probabilities for each window of each document")
    parser.add_argument('-input', type=str, required=True, help='train file')
    parser.add_argument('-db', type=str, required=True, help='database file')
    parser.add_argument('-emb', type=str, required=True, help='path to word embeddings')
    parser.add_argument('-window_size', type=int, default=3, help='window size') 
    parser.add_argument('-overwrite', action="store_true", default=False, help='overwrite existing DB') 
    parser.add_argument('-mode', nargs='+', choices=['extract','score'], help='extraction: computes windows and stores in db; score: compute the score for every word pair in the DB') 

    return parser

if __name__ == "__main__":
    #command line arguments    
    parser = get_parser()
    args = parser.parse_args()      
    print "[input @ %s | DB @ %s | window_size: %d | overwrite: %s]" % (args.input, args.db, args.window_size, args.overwrite)
    
    if "extract" in args.mode:
        ts = time.time()                        
        #create DB if it does not exist
        if not os.path.exists(args.db):
            print "[creating empty DB @ %s]" % args.db
            __create_sql(args.db, args.window_size)
        elif args.overwrite:     
            os.remove(args.db)
            print "[creating empty DB @ %s]" % args.db
            __create_sql(args.db, args.window_size)
        #open DB connection    
        db = sqlite3.connect(args.db)
        cursor = db.cursor()
        with open(args.input) as fid:
            for j, line in enumerate(fid):
                user, tweet = line.replace("\n","").replace("\"","").split("\t")
                tweet = tweet.decode("utf-8")
                word_pairs = extract_windows(tweet.split(), args.window_size)                
                __insert_wordpair(cursor, word_pairs)     
                if not j % 1000: 
                    sys.stdout.write("\r[extracted %d in ~%d minutes]" % (j,(time.time()-ts)/60))
                    sys.stdout.flush()  
        sys.stdout.write("\r[extracted %d in ~%d minutes]" % (j,(time.time()-ts)/60))
        sys.stdout.flush()  
        print "\n"
        db.commit()             
        db.close()   
    if "score" in args.mode:
        ts = time.time()                        
        BATCH_SIZE = 10000
        assert os.path.exists(args.db)        
        print "[loading embeddings @ %s]" % args.emb
        w2v = gensim.models.Word2Vec.load(args.emb)
        #open DB connection    
        db = sqlite3.connect(args.db)
        comm = """ SELECT word_pair FROM users WHERE word_pair NOT LIKE 'WINDOW_SIZE'"""
        select_cursor = db.cursor()
        update_cursor = db.cursor()
        select_cursor.execute(comm)
        rowz = select_cursor.fetchmany(BATCH_SIZE)
        j=0
        while len(rowz) > 0:            
            seqz = [x[0].split() for x in rowz]            
            scores = w2v.score(seqz,total_sentences=BATCH_SIZE)            
            __update_scores(update_cursor, rowz, scores.tolist())
            rowz = select_cursor.fetchmany(BATCH_SIZE)
            j+=1
            if not j % 1000: 
                sys.stdout.write("\r[scored %d in ~%d minutes]" % (j,(time.time()-ts)/60))
                sys.stdout.flush()  
        sys.stdout.write("\r[scored %d in ~%d minutes]" % (j,(time.time()-ts)/60))
        sys.stdout.flush()  
        db.commit()   
        