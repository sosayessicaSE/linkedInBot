import json
import os
import re
import textwrap
from datetime import datetime
from typing import Dict, List, Optional, Union
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages.ai import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompt_values import StringPromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from Levenshtein import distance

import src.strings as strings

load_dotenv()


class LLMLogger:
    
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    @staticmethod
    def log_request(prompts: Union[StringPromptValue, List[Dict]], parsed_reply: Dict[str, Dict]):
        calls_log = os.path.join(Path("data_folder/output"), "open_ai_calls.json")
        
        prompts_dict = {}

        if isinstance(prompts, StringPromptValue):
            prompts_dict = {"prompt_1": prompts.text}
        elif isinstance(prompts, list):
            for i, prompt in enumerate(prompts):
                if isinstance(prompt, dict):
                    prompts_dict[f"prompt_{i+1}"] = prompt.get('content', '')
                elif hasattr(prompt, 'content'):
                    prompts_dict[f"prompt_{i+1}"] = prompt.content
                else:
                    prompts_dict[f"prompt_{i+1}"] = str(prompt)
        else:
            prompts_dict = {"prompt_1": str(prompts)}

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract token usage details from the response
        token_usage = parsed_reply.get("usage_metadata", {})
        output_tokens = token_usage.get("output_tokens", 0)
        input_tokens = token_usage.get("input_tokens", 0)
        total_tokens = token_usage.get("total_tokens", 0)

        # Extract model details from the response
        response_metadata = parsed_reply.get("response_metadata", {})
        model_name = response_metadata.get("model_name", "")
        prompt_price_per_token = 0.00000015
        completion_price_per_token = 0.0000006

        # Calculate the total cost of the API call
        total_cost = (input_tokens * prompt_price_per_token) + (output_tokens * completion_price_per_token)

        # Create a log entry with all relevant information
        log_entry = {
            "model": model_name,
            "time": current_time,
            "prompts": prompts_dict,
            "replies": parsed_reply.get("content", ""),  # Response content
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
        }

        # Write the log entry to the log file in JSON format
        with open(calls_log, "a", encoding="utf-8") as f:
            json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
            f.write(json_string + "\n")



class LoggerChatModel:

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        # Call the LLM with the provided messages and log the response.
        reply = self.llm(messages)
        parsed_reply = self.parse_llmresult(reply)
        LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply)
        return reply

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Dict]:
        # Parse the LLM result into a structured format.
        content = llmresult.content
        response_metadata = llmresult.response_metadata
        id_ = llmresult.id
        usage_metadata = llmresult.usage_metadata
        parsed_result = {
            "content": content,
            "response_metadata": {
                "model_name": response_metadata.get("model_name", ""),
                "system_fingerprint": response_metadata.get("system_fingerprint", ""),
                "finish_reason": response_metadata.get("finish_reason", ""),
                "logprobs": response_metadata.get("logprobs", None),
            },
            "id": id_,
            "usage_metadata": {
                "input_tokens": usage_metadata.get("input_tokens", 0),
                "output_tokens": usage_metadata.get("output_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0),
            },
        }
        return parsed_result


class GPTAnswerer:
    def __init__(self, openai_api_key):
        self.llm_cheap = LoggerChatModel(
            ChatOpenAI(model_name="gpt-4o-mini", openai_api_key=openai_api_key, temperature=0.4)
        )
    
    @property
    def job_description(self):
        return self.job.description

    @staticmethod
    def find_best_match(text: str, options: List[str]) -> str:
        distances = [
            (option, distance(text.lower(), option.lower())) for option in options
        ]
        best_option = min(distances, key=lambda x: x[1])[0]
        return best_option

    @staticmethod
    def _remove_placeholders(text: str) -> str:
        return text.replace("PLACEHOLDER", "").strip()

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        return textwrap.dedent(template)

    def set_job(self, job):
        self.job = job
        self.job.set_summarize_job_description(self.summarize_job_description(self.job.description))

    def set_job_application_profile(self, job_application_profile):
        self.job_application_profile = job_application_profile
    def answer_question_numeric(self, question: str) -> str:
        # Define logic for answering numeric questions.
        # This could involve specific prompt templates or handling.
        prompt_template = "Provide a numeric answer to the following question: {question}"
        prompt = prompt_template.format(question=question)
        chain = self._create_chain(prompt)
        return chain.invoke({"question": question})
    def summarize_job_description(self, text: str) -> str:
        strings.summarize_prompt_template = self._preprocess_template_string(
            strings.summarize_prompt_template
        )
        prompt = ChatPromptTemplate.from_template(strings.summarize_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke({"text": text})
        return output
            
    def _create_chain(self, template: str):
        prompt = ChatPromptTemplate.from_template(template)
        return prompt | self.llm_cheap | StrOutputParser()
    
    def answer_question_textual_wide_range(self, question: str) -> str:
        # Define chains with hardcoded data for each section
        chains = {
            "self_identification": {
                "gender": "Female",
                "pronouns": "She",
                "veteran": "None",
                "disability": "N/A",
                "ethnicity": "Latin"
            },
            "legal_authorization": {
                "eu_work_authorization": "No",
                "us_work_authorization": "No",
                "requires_us_visa": "No",
                "requires_us_sponsorship": "No",
                "requires_eu_visa": "No",
                "legally_allowed_to_work_in_eu": "Yes",
                "legally_allowed_to_work_in_us": "Yes",
                "requires_eu_sponsorship": "No"
            },
            "work_preferences": {
                "remote_work": "Yes",
                "in_person_work": "No",
                "open_to_relocation": "No",
                "willing_to_complete_assessments": "Yes",
                "willing_to_undergo_drug_tests": "Yes",
                "willing_to_undergo_background_checks": "Yes"
            },
            "availability": {
                "notice_period": "1 Week"
            },
            "salary_expectations": {
                "salary_range_usd": "3000"
            },
            "education_details": [
                {
                    "degree": "Bachelor in Computer Science",
                    "university": "University Of the People",
                    "gpa": "n/a",
                    "graduation_year": "2028",
                    "field_of_study": "Computer Science",
                    "exam": {"Engineering": "n/a"}
                },
                {
                    "degree": "Software Engineering",
                    "university": "IAE Colonia",
                    "gpa": "n/a",
                    "graduation_year": "2025",
                    "field_of_study": "Software Development",
                    "exam": {"Engineering": "n/a"}
                },
                {
                    "degree": "Analyst Programmer",
                    "university": "CEI Maldonado",
                    "gpa": "n/a",
                    "graduation_year": "2024",
                    "field_of_study": "Software Development",
                    "exam": {"Engineering": "100/100"}
                },
                {
                    "degree": "Quality Engineering",
                    "university": "Globant",
                    "gpa": "n/a",
                    "graduation_year": "2023",
                    "field_of_study": "Quality Engineering",
                    "exam": {"QE": "n/a"}
                },
                {
                    "degree": "English Language",
                    "university": "Dickens Institute",
                    "gpa": "n/a",
                    "graduation_year": "2017",
                    "field_of_study": "English Language",
                    "exam": {"Proficiency": "n/a"}
                }
            ]
        }
        
        # Check if the question matches any predefined categories
        matched_chain = None
        for section, content in chains.items():
            if re.search(r'\b' + re.escape(section) + r'\b', question, re.IGNORECASE):
                matched_chain = content
                break

        if matched_chain:
            return json.dumps(matched_chain, indent=2)
        else:
            return "No matching data found."
