import json
from langchain_community.chat_models import ChatAnyscale
from langchain.prompts.prompt import PromptTemplate
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory

from .utils import Chat
from . import prompts


MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"
FEEDBACK_MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"
MAX_TOKENS_PER_QUESTION = 100


class LLMClient:
    def __init__(self):
        self.llm = ChatAnyscale(model_name=MODEL, max_tokens=MAX_TOKENS_PER_QUESTION)

        memory = ConversationBufferMemory()
        self.prompt = PromptTemplate(
            input_variables=["history", "input"], template=prompts.SYSTEM_PROMPT
        )

        self.conversation = ConversationChain(llm=self.llm, memory=memory, prompt=self.prompt)

    def get_json_from_response(self, response, n=0):
        if n > 5:
            return {}

        try:
            return json.loads(response)
        except:
            pass

        try:
            response = response[response.find("{") :]
            response = response[: response.rfind("}") + 1]
            return json.loads(response)
        except:
            try:
                response = response[response.find("{") :]
                return self.get_json_from_response(response, n + 1)
            except:
                response = response[: response.rfind("}") + 1]
                return self.get_json_from_response(response, n + 1)

    def get_question(self, question):
        data = self.conversation.invoke(input=question)
        data = self.get_json_from_response(data["response"])

        interview_ended = data["type"] == "Interview Ended"
        text = data["text"]

        return interview_ended, text

    def get_feedback(self, user_name, chats: list[Chat]):
        chats_data = [chat.to_dict() for chat in chats]
        text = (
            f"The interview has finished. Candidate name: {user_name}. Chat History: {chats_data}"
        )
        text = f"{prompts.ANALYSIS_PROMPT}\n\n{text}"

        llm = ChatAnyscale(model_name=FEEDBACK_MODEL)
        response = llm.invoke(input=text)
        response = self.get_json_from_response(response.content)

        return response


if __name__ == "__main__":
    chatbot = LLMClient()

    job_description = "We are looking for a Software Developer to build and implement functional programs. You will work with other Developers and Product Managers throughout the software development life cycle. In this role, you should be a team player with a keen eye for detail and problem-solving skills. If you also have experience in Agile frameworks and popular coding languages (e.g. JavaScript), we’d like to meet you. Your goal will be to build efficient programs and systems that serve user needs. Responsibilities Work with developers to design algorithms and flowcharts Produce clean, efficient code based on specifications Integrate software components and third-party programs Verify and deploy programs and systems Troubleshoot, debug and upgrade existing software Gather and evaluate user feedback Recommend and execute improvements Create technical documentation for reference and reporting"
    company_name = "Mecha Tech"
    user_name = "Rushil Gupta"

    text = f"Company Name: {company_name}\nJob Description: {job_description}\n Candidate Name: {user_name}"
    with open("interview/chats.json", "r") as f:
        chats_data = json.load(f)
    text = f"The interview has finished. Candidate name: {user_name}. Chat History: {chats_data}"
    text = f"{prompts.ANALYSIS_PROMPT}\n\n{text}"

    llm = ChatAnyscale(model_name=FEEDBACK_MODEL)
    response = llm.invoke(input=text)
    response = chatbot.get_json_from_response(response.content)
    print(json.dumps(response))
