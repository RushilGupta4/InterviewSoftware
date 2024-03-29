import json
import logging

from langchain_community.chat_models import ChatAnyscale
from langchain.prompts.prompt import PromptTemplate
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory

from .utils import Chat
from . import prompts


MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"
FEEDBACK_MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"
MAX_TOKENS_PER_QUESTION = 100


logger = logging.getLogger(__name__)
print = logger.info


class LLMClient:
    def __init__(self, interview_data, user_name):
        self.llm = ChatAnyscale(model_name=MODEL, max_tokens=MAX_TOKENS_PER_QUESTION)

        prompt_template = (
            prompts.SYSTEM_PROMPT.replace("{company_name}", interview_data["company_name"])
            .replace("{job_description}", interview_data["job_description"])
            .replace("{user_name}", user_name)
        )
        memory = ConversationBufferMemory()
        self.prompt = PromptTemplate(input_variables=["history", "input"], template=prompt_template)

        self.conversation = ConversationChain(llm=self.llm, memory=memory, prompt=self.prompt)

    async def get_json_from_response(self, response: str, n=0) -> dict:
        if n > 10:
            print("Recursion limit reached. Potential issue with deeply nested or malformed JSON.")
            return {}

        try:
            print(f"Initial JSON loading attempt (recursion level: {n})")
            data = json.loads(response)
            print("JSON loading successful!")
            return data  # Success!
        except json.JSONDecodeError as e:
            print(f"JSON decoding error: {e}")
            print(f"Response content:\n{response}")

        # More refined string manipulation (if necessary)
        try:
            start_index = response.find("{")
            end_index = response.rfind("}") + 1

            if start_index == 0 and end_index == len(response):  # Check if entire string is JSON
                start_index += 1
                end_index -= 1

            if start_index != -1 and end_index != 0:  # Check if indices are valid
                potential_json = response[start_index:end_index]
                print(f"Extracted potential JSON:\n{potential_json}")
                return await self.get_json_from_response(potential_json, n + 1)
            else:
                print("Unable to extract valid JSON substring.")
        except IndexError:
            print("Error during string manipulation.")

        print("Failed to extract JSON.")
        return {}

    async def start_interview(self) -> tuple[bool, str]:
        first_chat = "Hi, let's start the interview."
        interview_ended, response = await self.get_question(first_chat)
        return interview_ended, response

    async def get_question(self, question: str) -> tuple[bool, str]:
        data = await self.conversation.ainvoke(input=question)
        data = await self.get_json_from_response(data["response"])

        interview_ended = data.get("type", "") == "Interview Ended"
        text = data.get("text", "")

        return interview_ended, text

    async def get_feedback(self, user_name: str, chats: list[Chat]) -> dict:
        chats_data = [chat.to_dict() for chat in chats]
        text = (
            f"The interview has finished. Candidate name: {user_name}. Chat History: {chats_data}"
        )
        text = f"{prompts.ANALYSIS_PROMPT}\n\n{text}"

        llm = ChatAnyscale(model_name=FEEDBACK_MODEL)
        response = await llm.ainvoke(input=text)
        response = await self.get_json_from_response(response.content)

        return response


if __name__ == "__main__":

    job_description = "We are looking for a Software Developer to build and implement functional programs. You will work with other Developers and Product Managers throughout the software development life cycle. In this role, you should be a team player with a keen eye for detail and problem-solving skills. If you also have experience in Agile frameworks and popular coding languages (e.g. JavaScript), we’d like to meet you. Your goal will be to build efficient programs and systems that serve user needs. Responsibilities Work with developers to design algorithms and flowcharts Produce clean, efficient code based on specifications Integrate software components and third-party programs Verify and deploy programs and systems Troubleshoot, debug and upgrade existing software Gather and evaluate user feedback Recommend and execute improvements Create technical documentation for reference and reporting"
    company_name = "Mecha Tech"
    user_name = "Rushil Gupta"

    interview_data = {
        "company_name": company_name,
        "job_description": job_description,
    }

    chatbot = LLMClient(interview_data, user_name)

    print(chatbot.get_question("Hi, let's start the interview."))
