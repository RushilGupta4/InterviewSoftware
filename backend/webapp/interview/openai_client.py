import json
from threading import Event
import openai
from . import prompts

MODEL = "gpt-4-turbo-preview"


def get_assistant_id():
    client = openai.Client()
    assistants = client.beta.assistants.list()

    filtered_assistants = list(
        filter(lambda x: x.instructions == prompts.SYSTEM_PROMPT, assistants)
    )
    if len(filtered_assistants) > 0:
        return filtered_assistants[-1].id

    assistant = client.beta.assistants.create(
        model=MODEL,
        name="Interview Assistant",
        instructions=prompts.SYSTEM_PROMPT,
    )
    return assistant.id


class OpenAIClient:
    def __init__(self):
        self.client = openai.Client()
        self.assistant_id = get_assistant_id()
        self.event = Event()

        self.thread = self.client.beta.threads.create()

    def ask(self, question, instructions=None):
        message = self.client.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=question,
        )

        if instructions:
            run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=self.assistant_id,
                instructions=instructions,
            )

        else:
            run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=self.assistant_id,
            )

        while True:
            run_status = self.client.beta.threads.runs.retrieve(
                thread_id=self.thread.id, run_id=run.id
            )

            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                print(f"Run failed: {run_status.last_error}")
                break

            self.event.wait(1)

        messages = self.client.beta.threads.messages.list(thread_id=self.thread.id)
        assistant_response = messages.data[0].content[0].text.value
        assistant_response = json.loads(assistant_response)
        return assistant_response

    def get_question(self, transcript):
        data = self.ask(transcript)
        interview_ended = data["type"] == "Interview Ended"
        text = data["text"]

        return interview_ended, text


if __name__ == "__main__":
    chatbot = OpenAIClient()

    response = chatbot.get_question(
        "We are looking for a Software Developer to build and implement functional programs. You will work with other Developers and Product Managers throughout the software development life cycle. In this role, you should be a team player with a keen eye for detail and problem-solving skills. If you also have experience in Agile frameworks and popular coding languages (e.g. JavaScript), we’d like to meet you. Your goal will be to build efficient programs and systems that serve user needs. Responsibilities Work with developers to design algorithms and flowcharts Produce clean, efficient code based on specifications Integrate software components and third-party programs Verify and deploy programs and systems Troubleshoot, debug and upgrade existing software Gather and evaluate user feedback Recommend and execute improvements Create technical documentation for reference and reporting",
    )

    print(response)
