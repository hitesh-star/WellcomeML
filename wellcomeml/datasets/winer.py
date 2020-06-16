# WiNER: A Wikipedia Annotated Corpus for Named Entity Recognition
# https://www.aclweb.org/anthology/I17-1042/

import tarfile
import os
from tqdm import tqdm 
import json
import random

from wellcomeml.datasets.download import check_cache_and_download
from wellcomeml.logger import logger

def yield_article_entities(f):
    article_entities = []
    for i, line in enumerate(f):
        line = line.decode("utf-8").replace('\n', '') # because line is of type bytes
        if line.startswith('ID '):
            article_id = line.split('ID ')[1]
        else:
            entities_data = line.replace('\t', ' ')
            sentence_id, begin, end, ent_type = entities_data.split(' ')
            # The data is stored as strings, but they are all numerical
            # and sentence id = 3 refers to the 2nd sentence in this article
            # so for querying the list of sentences in an article
            # later it is useful to have this as an integer
            yield (article_id, int(sentence_id), int(begin), int(end), int(ent_type))

def create_train_test(
    NE_path, vocab_path, docs_path,
    train_processed_path, test_processed_path,
    n_sample, prop_train, rand_seed=42
    ):
    """
    Function to transform the raw WiNER datasets into training
    and testing datasets suitable for training a NER model.
    This NE_path file gives the entities, but they need to be linked
    to the sentences they came from, which involves translating
    them from the vectorised form in the docs_path file
    using the vocab_path file.

    NE_path: File path to the WiNER raw data named entities
    vocab_path: File path to the WiNER raw data vocab dictionary
    docs_path: File path to the WiNER raw data documents texts
            (words coded according to the vocab)
    train_processed_path: Output file path for the training data
    test_processed_path: Output file path for the testing data
    n_sample: Number of files to get data from, each file contains about 1000 documents
    prop_train: Proportion of the file sample that will be in the training data

    Utilise the three datasources to get the entities from a sample
    of documents and save to a training and testing dataset files
    in the form:

    ID 12345

    John Smith PERSON
    rejects O
    German LOC
    call O
    
    Next 0
    sentence 0

    ID 444

    Next
    document
    """

    # Set the random seed for taking a sample
    random.seed(rand_seed)
    n_train = round(prop_train*n_sample)

    # Make a dictionary for the entities for every article
    # in the form
    # entities = {article_id: {sentence_id:[[0, 4, 0], [18, 25, 1]]}}
    # The sentence id is which number sentence (e.g. 1st, 2nd) the entities
    # are from in the whole document

    logger.info("Creating entities dictionary from {}".format(NE_path))
    entities = {}
    with tarfile.open(NE_path, "r:bz2") as tar:
        tar_names = tar.getnames()
        # Some nuances of the tarred folders contains 
        tar_names = [name for name in tar_names \
            if 'CoarseNE/' in name and 'CoarseNE/._' not in name]
        for tar_name in tqdm(tar_names):
            member = tar.getmember(tar_name)
            f = tar.extractfile(member)
            sentence_entities = {}
            for (article_id, sentence_id, begin, end, ent_type) in yield_article_entities(f):
                if entities.get(article_id):
                    if entities[article_id].get(sentence_id):
                        entities[article_id][sentence_id].append([begin, end, ent_type])
                    else:
                        entities[article_id][sentence_id] = [[begin, end, ent_type]]
                else:
                    entities[article_id] = {sentence_id : [[begin, end, ent_type]]}

    # Create id2word from vocab file
    # The WiNER documentation states that the line number is the word id
    logger.info("Creating id2word dictionary from {}".format(vocab_path))
    id2word = {}
    with open(vocab_path, "r") as vocab:
        for i, line in enumerate(vocab):
            id2word[i] = line.split(' ')[0]

    # Go into a sample of the vectorised document files, see if there are any entities 
    # found for it in the 'entities' dictionary, and if so translate
    # the vectorised document into words using 'id2word'
    # Saving a certain proportion to the test file and train file.
    logger.info("Creating token and tag from {}".format(docs_path))
    with tarfile.open(docs_path, "r:bz2") as tar_docs, \
            open(train_processed_path, 'w') as train_file, \
            open(test_processed_path, 'w') as test_file:
        tar_names = tar_docs.getnames()
        # Some nuances of the tarred folders contains 
        tar_names = [name for name in tar_names \
            if 'Documents/Documents/' in name and 'Documents/Documents/._' not in name]
        # Take a sample of the relevant files
        tar_name_sample = random.sample(tar_names, n_sample)
        for i, tar_name in tqdm(enumerate(tar_names)):
            member = tar_docs.getmember(tar_name)
            # Which output file to save the results in
            if i < n_train:
                output_file = train_file
            else:
                output_file = test_file
            # Extract the texts for this file if there is any given
            f = tar_docs.extractfile(member)
            if f:
                content = f.read().decode('utf-8', errors='ignore')
                # Each article in the document is separated by the article ID, e.g. 'ID 123'
                articles = content.replace('\t', ' ').split('ID ')
                articles = articles[1:]
                for article in articles:
                    sentences = article.split('\n')
                    article_id = sentences[0]
                    article_entities = entities.get(article_id)
                    # Only save entity information if we found that
                    # this document indeed had entities!
                    if article_entities:
                        output_file.write('ID ' + article_id)
                        output_file.write('\n\n')
                        # The first and last sentences can be blank due to splitting
                        if sentences[-1]=='':
                            sentences = sentences[1:-1]
                        else:
                            sentences = sentences[1:]
                        # In the documents each sentence is a string of
                        # numbers corresponding to words in id2word, convert
                        # this string into a list of numbers for each sentence
                        sent_wordidx = [l.split(' ') for l in sentences]
                        # Go through each of the entites for this article
                        # and translate the word ids to their words to create
                        # the tokens and each entity.
                        for sentid, sentence_entities in article_entities.items():
                            if len(sent_wordidx) > int(sentid):
                                # Translate the list of words ids for this sentence into 
                                # the words using id2word
                                tokens = [id2word[int(s)] for s in sent_wordidx[int(sentid)]]
                                # Every word in the sentence is classed as an outside word 
                                # until found otherwise from the entity list
                                tags = ['O']*len(tokens)
                                for begin, end, ent_type in sentence_entities:
                                    # For entities that spread over multiple words
                                    # it should be clear which word is the start of the 
                                    # entity and which is the end
                                    tags[(begin+1):(end-1)] = [str(ent_type) + '-I']*(end-1-begin-1)
                                    tags[end-1] = str(ent_type) + '-E'
                                    tags[begin] = str(ent_type) + '-B'
                                for token, tag in list(zip(tokens, tags)):
                                    output_file.write(' '.join([token, tag]))
                                    output_file.write('\n')
                            output_file.write('\n')

def _load_data_spacy(data_path, inc_outside=True, merge_entities=True):

    # Load data in Spacy format:
    # X = list of sentences (plural) / documents ['the cat ...', 'some dog...', ...]
    # Y = list of list of entity tags for each sentence [[{'start': 36, 'end': 46, 'label': 'PERSON'}, {..}, ..], ... ]
    # inc_outside = False: don't include none-entities in the output
    # merge_entities if entities span over multiple tags do you want to merge them or not
    # e.g. John 3-B Smith 3-E -> John Smith 3

    X = []
    Y = []
    with open(data_path) as f:
        lines = f.read().split('ID ')
        for line in lines:
            if line != '':
                sentences = line.split('\n\n')
                # The first and last sentence is blank due to splitting
                sentences = sentences[1:-1]
                for sentence in sentences:
                    char_i = 0 # A counter to populate the start and end character indexes for each entity
                    sentence_text = ''
                    sentence_tags = []
                    entities = sentence.split('\n') # ['Gibraltar 3-B', 'has O', 'a O', ...]
                    tokens, tags = zip(*[tuple(ee) for ee in [e.split(' ') for e in entities]])
                    if merge_entities:
                        # if entities span over multiple words merge them into one token
                        # e.g. John 3-B Smith 3-E -> John Smith 3
                        prev_B = 0 # Counter for index of last entity beginning
                        group_tags = []
                        for i, tag in enumerate(tags):
                            if tag[-2:]=='-E':
                                group_tags.append((prev_B, i+1))
                            if tag[-2:]=='-B':
                                if len(tags)!=(i+1) and (tags[i+1][-2:]=='-I' or tags[i+1][-2:]=='-E'):
                                    prev_B = i
                                else:
                                    group_tags.append((i, i+1))
                            if tag=='O':
                                group_tags.append((i, i+1))
                        tags_joined = [' '.join(tags[b:e])[0] for b,e in group_tags]
                        tokens_joined = [' '.join(tokens[b:e]) for b,e in group_tags]
                    else:
                        tags_joined = [t[0] for t in tags]
                        tokens_joined = tokens
                    for tag, token in zip(tags_joined, tokens_joined):
                        sentence_text += token + ' '
                        if tag!='O' or inc_outside:
                            sentence_tags.append({'start': char_i, 'end': char_i+len(token), 'label': tag})
                        char_i += len(token) + 1 # plus 1 for the space separating
                    if sentence_tags!=[]:
                        X.append(sentence_text)
                        Y.append(sentence_tags)

    return X, Y

def load_winer(split='train', shuffle=True, inc_outside=True, merge_entities=True):
    path = check_cache_and_download("winer")

    if split == 'train':
        train_data_path = os.path.join(path, "train.txt")
        X, Y = _load_data_spacy(train_data_path, inc_outside=inc_outside, merge_entities=merge_entities)
    elif split == 'test':
        test_data_path = os.path.join(path, "test.txt")
        X, Y = _load_data_spacy(test_data_path, inc_outside=inc_outside, merge_entities=merge_entities)
    else:
        raise ValueError(f"Split argument {split} is not one of train, test or evaluate")

    if shuffle:
        data = list(zip(X, Y))
        random.shuffle(data)
        X, Y = zip(*data)

    return X, Y

if __name__ == '__main__':

    path = check_cache_and_download("winer")

    train_processed_path = os.path.join(path, "train.txt")
    test_processed_path = os.path.join(path, "test.txt")

    if not os.path.exists(train_processed_path):
        # Since this has been done once it shouldnt need to be done again, 
        # including here for completeness or in th case we want to increase 
        # the sample size
        logger.info("No {} training data file found, generating ...".format(train_processed_path))

        NE_path = os.path.join(path, "CoarseNE.tar.bz2")
        docs_path = os.path.join(path, "Documents.tar.bz2")
        vocab_path = os.path.join(path, "document.vocab")

        # Create the train/test data
        n_sample = 10
        prop_train = 0.7

        create_train_test(
            NE_path, vocab_path, docs_path,
            train_processed_path, test_processed_path,
            n_sample, prop_train, rand_seed=42
            )
    else:
        logger.info("Training and test data found")

