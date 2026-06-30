from langchain_text_splitters import RecursiveCharacterTextSplitter,CharacterTextSplitter,TokenTextSplitter


def fixed_len_splitter(document, chunk_size, chunk_overlap):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size = chunk_size,
        chunk_overlap = chunk_overlap,
    )
    split_docs = splitter.split_documents(document)
    print(f"분할된 chunk 수: {len(split_docs)}")
    return split_docs


def char_splitter(document):
    splitter = CharacterTextSplitter(
        separator="\n\n",         
        chunk_size=500,
        chunk_overlap=50,
        in_separator_regex = False
    )
    split_docs = splitter.split_documents(document)
    print(f"분할된 chunk 수: {len(split_docs)}")
    return split_docs



## 한국어 적합
def Token_splitter(document):
    splitter = TokenTextSplitter(
        encoding_name="o200k_base",                 
        chunk_size=500,
        chunk_overlap=50,
    )
    split_docs = splitter.split_documents(document)
    print(f"분할된 chunk 수: {len(split_docs)}")
    return split_docs
