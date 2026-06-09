# Data Product Overview
Retrieve data from Jira (Atlassian) via its API, chunk and "vectorise" the free text fields like summary, comment and description which can then be stored within "pgvector" database.

It should created within the "engineering" domain and use the "ecommerce-demo" infrastructure profile, the Nextdata instance is located at: https://app.demo.nextopia.dev/

Data product name should be jira-issues.

# Input
The best endpoint for Jira is likely "/rest/api/3/search/jql", it supports pagination via the "nextPageToken" field. There will be a NXD infrastructure profile service call "jira-api" (driver: nxd:api:0.1.0, context: API) which will hold the username, url and token used for authentication (don't worry it is suitable for Jira). I would like to filter to only retrieve specific "project" issues (ones label "NXD"). Do not include an expectation on the input.

# Output
The data should be stored within a pgvector instance, specifically the service call "pgvector" (driver: nxd:pgvector:1.0.0, context: PGVector). The schema used should called "public" and there should be one output table, focused on embeddings. 

# Transformation
All issues will be retrieved. Alongside free text fields like summary, comment and description also retrieve core fields like id, date - things that would be useful to store as metadata within a vector store.

Free text should be chunked with RecursiveCharacterTextSplitter (from langchain_text_splitters import RecursiveCharacterTextSplitter) with the size of 512.

The ideal embedding model is "all-MiniLM-L6-v2" provided by "HuggingFaceEmbeddings".

The free text fields are to be "vectorised' and other the other fields can be used as metadata.

The class PGVectorStore from "langchain_postgres" should be used for writing data since you can write to specific tables. The structure of this table is mostly dictated by PGVectorStore and the resulting NXD model should be align with it.

The transformation should run on a four hourly basis.

# Models
There should be one model for the API input which should reflect what information is gathered from the API response. The output should also feature a single model which aligns with the schema which get seeded within "pgvector" specifically pg_engine.init_vectorstore_table.

Complex types should be avoided since within semantic models since they are not fully compatibile, in the interim utilse strings within NXD sematic models to represent complex types.

# Validation
There is no need to run any validation or smoke tests upon completion of the implementation, I will perform this myself.
