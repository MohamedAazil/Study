I want to build an ai tool that allows students to study effectively 
These are the features I want: 
1. Students should be able to onboard their existing time table using a pdf/custom inputs and we need to shoew them sa timetabe
2. Students/Teachers should be able to create tasks for each day like a to-do list, this list should be seen in 2 places, a dedicated to-do list app and also be connected to the timetable (based on subjects). At the end of the day a report of this should be sent to the parents in their login. 
3. A dedicated space to store past papers, subject materials, textbook pdfs and so on 
4. Finally and most importantly 2 AI Agent with the following features:
    - A RAG Chat Interface with grounding. Here the AI Agent will answer students' doubts using the text book and study materials (not the past papers) with proper grounding and citations. They should be able to click on the citation and to the exact excerpt of the textbook the Ai ansewred from.
    - Examiner Agent. This will be a separate interface/mode where if the student says he wants to practice questions based on a certain topic, the agent will go through the a separate RAG Vector Index with past paper questions and asnwers, create a question paper on the spot (based on the total marks and difficulty level provided by the student). The student will complete the test and give back the answers as pdf/text/hand written answer images. The Agent should grade the student and tell where to focus. 


Tech Stack: 
- Backend - Python FastAPI 
- Frontend - React TS
- DB - Supabase Postgres
- Vector Index - Pinecone
- Object Store - Supabase
- Agent Framework - Langchain/Langgraph
