import json
from openai import OpenAI


class OpenAIClient:
    def __init__(self):
        """
        Initializes the chatbot with an empty chat log.
        """
        self.client = OpenAI()
        self.chat_log = []  # Initialize an empty chat log
        self.tokens_used = 0  # Initialize the number of tokens used to 0

    def ask(self, message, model="gpt-4", temperature=0.7, max_tokens=150):
        """
        Sends a message to the chatbot and appends both the message and response to the chat log.
        
        Args:
        - message (str): The message or question from the user.
        - model (str): The model to use, defaults to "gpt-4".
        - temperature (float): Controls randomness in the response. Closer to 1 means more random.
        - max_tokens (int): The maximum number of tokens to generate in the response.
        
        Returns:
        - str: The response from the chatbot.
        """
        self._add_to_chat_log("user", message)
        response = self.client.ChatCompletion.create(
            model=model,
            response_format={ "type": "json_object" },
            messages=self.chat_log,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Extract the text from the response and add it to the chat log
        response_json = response["choices"][0]["message"]['content']
        response_text = json.loads(response_json)

        tokens = response["choices"][0]["message"]["num_tokens"]
        self._add_to_chat_log("assistant", response_text, tokens)
        
        return response_text

    def _add_to_chat_log(self, speaker, message, tokens=0):
        """
        Adds a message to the chat log with the appropriate speaker label.
        
        Args:
        - speaker (str): The speaker, "Human" or "AI".
        - message (str): The message content.
        - tokens (int): The number of tokens used in the response.
        """
        self.chat_log.append({"role": speaker, "content": message})
        self.tokens_used += tokens

# Example usage:
api_key = 'YOUR_API_KEY'  # Replace with your actual OpenAI API key
chatbot = OpenAIClient()
response = chatbot.ask("What's the weather like today?")
print(f"GPT-4: {response}")

# Subsequent calls to chatbot.ask will remember the context of the conversation.
