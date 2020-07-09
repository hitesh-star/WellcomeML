from wellcomeml.datasets.conll import _load_data_spacy


def test_length():
    X, Y = _load_data_spacy('tests/test_data/test_conll', inc_outside=True)

    assert len(X) == len(Y) and len(X) == 4


def test_entity():
    X, Y = _load_data_spacy('tests/test_data/test_conll', inc_outside=False)

    start = Y[0][0]['start']
    end = Y[0][0]['end']

    assert X[0][start:end] == 'LEICESTERSHIRE'


def test_no_outside_entities():
    X, Y = _load_data_spacy('tests/test_data/test_conll', inc_outside=False)

    outside_entities = [entity for entities in Y for entity in entities if entity['label'] == 'O']

    assert len(outside_entities) == 0
