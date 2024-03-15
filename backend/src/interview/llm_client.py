import json
from langchain_community.chat_models import ChatAnyscale
from langchain.prompts.prompt import PromptTemplate
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferWindowMemory

from .utils import Chat
from . import prompts

MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"


class LLMClient:
    def __init__(self, model_name=MODEL):
        self.llm = ChatAnyscale(model_name=model_name)
        self.prompt = PromptTemplate(
            input_variables=["history", "input"], template=prompts.SYSTEM_PROMPT
        )
        self.conversation = ConversationChain(
            llm=self.llm, memory=ConversationBufferWindowMemory(k=8), prompt=self.prompt
        )

    def get_question(self, question):
        data = self.conversation.predict(input=question)
        data = json.loads(data)
        interview_ended = data["type"] == "Interview Ended"
        text = data["text"]

        return interview_ended, text

    def get_feedback(self, user_name, chats: list[Chat]):
        chats_data = [chat.to_dict() for chat in chats]
        text = (
            f"The interview has finished. Candidate name: {user_name}. Chat History: {chats_data}"
        )
        text = f"{prompts.ANALYSIS_PROMPT}\n\n{text}"
        data = self.llm.predict(input=text)
        return data


if __name__ == "__main__":
    chatbot = LLMClient()

    job_description = "We are looking for a Software Developer to build and implement functional programs. You will work with other Developers and Product Managers throughout the software development life cycle. In this role, you should be a team player with a keen eye for detail and problem-solving skills. If you also have experience in Agile frameworks and popular coding languages (e.g. JavaScript), we’d like to meet you. Your goal will be to build efficient programs and systems that serve user needs. Responsibilities Work with developers to design algorithms and flowcharts Produce clean, efficient code based on specifications Integrate software components and third-party programs Verify and deploy programs and systems Troubleshoot, debug and upgrade existing software Gather and evaluate user feedback Recommend and execute improvements Create technical documentation for reference and reporting"
    company_name = "Mecha Tech"
    user_name = "Rushil Gupta"
    first_chat = f"Company Name: {company_name}\nJob Description: {job_description}\n Candidate Name: {user_name}"

    response = chatbot.get_question(first_chat)

    print(response)
