I want to build an app that will allow an user to import any arbitrary strucutred data like, csv, tsv, excel into a database using an AI

agent,

Here's how I am thinking it would work,

user will upload a document, for each document a user can click on import, that will run the agentic import pipeline

Here's how the import pipeline would work

It will take the file and create a profile of a file that will be passed to the llm in the next step so that the llm can create an import script

then the import script will be run and if there are any errors it it will fix the import script, after the import is done It will validate the import

LLm can choose to ask if there is anything ambiguous to clarify things.

So from the main page a user can create  a project and inside the project inside the project they can start a new improt by selecting already uploaded documents or uploading new documents

the import pipeline will run for only one document if user select's multiple documents then it will creat multiple import pipeline

There are going to be several tabs in a project, the main tab will show the imported data, os on the left side there is going to be the list of tables and

on the right side it will show the table data

second tab will show the imports

third tab will show the schema diagram
