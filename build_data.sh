#!/bin/bash -e

#When trying to learning embeddings for a large number of users, one may want to parallelize training by splitting the users into different blocks. `n_splits' specifies the number of partitions of the training data (1 is the default)
n_splits=1
if [ ! -z "$1" ]
  then
    n_splits=$1    
    echo "### n_splits:"$1 
fi
clear
printf "cleaning up...\n"
rm DATA/tmp/*.* || true
rm DATA/out/*.* || true

###########################
# SETUP (edit these paths)
# 
# user documents
# IMPORTANT the system assumes the documents:
# 1. can be white-space tokenized 
# 2. are sorted by user (i.e., all the documents of a given user appear sequentially in the file)
# 3. have at least MIN_MSG_SIZE=4 words (see build_data.py)
# 
DOCS="DATA/txt/user_corpus.txt"
# DOCS="DATA/txt/sample.txt"
# embeddings
WORD_EMBEDDINGS_TXT="DATA/embeddings/embs_emoji_2_400.txt"
OUTPUT_PATH="DATA/tmp/train_data.pkl"
#
###########################

###########################
# OPTIONS
#
MAX_VOCAB_SIZE=50000
MIN_DOCS=20 #reject users with less than this number of documents
#
##########################

### ACTION!

printf "\n#### Build Training Data #####\n"
python code/build_train.py -input ${DOCS} -emb ${WORD_EMBEDDINGS_TXT} -output ${OUTPUT_PATH} -min_docs ${MIN_DOCS} -vocab_size ${MAX_VOCAB_SIZE}

if (($n_splits > 1 )); 
	then
		printf "\n#### Sort and Split Training Data #####\n"
		python code/sort_split.py -input ${OUTPUT_PATH} -n_splits ${n_splits} 
fi