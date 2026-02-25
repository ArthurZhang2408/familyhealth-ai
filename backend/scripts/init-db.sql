-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create mem0 database
SELECT 'CREATE DATABASE mem0_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mem0_db')\gexec
