import base64
import json
import os
import random
import re
import tempfile
import time
import traceback
from datetime import date
from typing import List, Optional, Any, Tuple
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver import ActionChains
import src.utils as utils

class LinkedInEasyApplier:
    def __init__(self, driver: Any, resume_dir: Optional[str], set_old_answers: List[Tuple[str, str, str]], gpt_answerer: Any):
        self.driver = driver
        self.resume_path = resume_dir if resume_dir and os.path.exists(resume_dir) else None
        self.set_old_answers = set_old_answers
        self.gpt_answerer = gpt_answerer
        self.all_data = self._load_questions_from_json()

    def _load_questions_from_json(self) -> List[dict]:
        output_file = 'answers.json'
        try:
            with open(output_file, 'r') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("JSON file format is incorrect. Expected a list of questions.")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            data = []
        except Exception:
            tb_str = traceback.format_exc()
            raise Exception(f"Error loading questions data from JSON file: \nTraceback:\n{tb_str}")
        return data

    def job_apply(self, job: Any):
        self.driver.get(job.link)
        time.sleep(random.uniform(3, 5))
        try:
            easy_apply_button = self._find_easy_apply_button()
            job.set_job_description(self._get_job_description())
            job.set_recruiter_link(self._get_job_recruiter())
            actions = ActionChains(self.driver)
            actions.move_to_element(easy_apply_button).click().perform()
            self.gpt_answerer.set_job(job)
            self._fill_application_form(job)
        except Exception:
            tb_str = traceback.format_exc()
            self._discard_application()
            raise Exception(f"Failed to apply to job! Original exception: \nTraceback:\n{tb_str}")

    def _find_easy_apply_button(self) -> WebElement:
        for attempt in range(2):
            self._scroll_page()
            buttons = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.XPATH, '//button[contains(@class, "jobs-apply-button") and contains(., "Easy Apply")]')
                )
            )
            for index in range(len(buttons)):
                try:
                    button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, f'(//button[contains(@class, "jobs-apply-button") and contains(., "Easy Apply")])[{index + 1}]')
                        )
                    )
                    return button
                except Exception:
                    continue
            if attempt == 0:
                self.driver.refresh()
                time.sleep(3)
        raise Exception("No clickable 'Easy Apply' button found")

    def _get_job_description(self) -> str:
        try:
            see_more_button = self.driver.find_element(By.XPATH, '//button[@aria-label="Click to see more description"]')
            actions = ActionChains(self.driver)
            actions.move_to_element(see_more_button).click().perform()
            time.sleep(2)
            return self.driver.find_element(By.CLASS_NAME, 'jobs-description-content__text').text
        except NoSuchElementException:
            tb_str = traceback.format_exc()
            raise Exception(f"Job description 'See more' button not found: \nTraceback:\n{tb_str}")
        except Exception:
            tb_str = traceback.format_exc()
            raise Exception(f"Error getting Job description: \nTraceback:\n{tb_str}")

    def _get_job_recruiter(self) -> str:
        try:
            hiring_team_section = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//h2[text()="Meet the hiring team"]'))
            )
            recruiter_element = hiring_team_section.find_element(By.XPATH, './/following::a[contains(@href, "linkedin.com/in/")]')
            return recruiter_element.get_attribute('href')
        except Exception:
            return ""

    def _scroll_page(self) -> None:
        scrollable_element = self.driver.find_element(By.TAG_NAME, 'html')
        utils.scroll_slow(self.driver, scrollable_element, step=300, reverse=False)
        utils.scroll_slow(self.driver, scrollable_element, step=300, reverse=True)

    def _fill_application_form(self, job):
        while True:
            self.fill_up(job)
            if self._next_or_submit():
                break

    def _next_or_submit(self) -> bool:
        next_button = self.driver.find_element(By.CLASS_NAME, "artdeco-button--primary")
        button_text = next_button.text.lower()
        if 'submit application' in button_text:
            self._unfollow_company()
            time.sleep(random.uniform(1.5, 2.5))
            next_button.click()
            time.sleep(random.uniform(1.5, 2.5))
            return True
        time.sleep(random.uniform(1.5, 2.5))
        next_button.click()
        time.sleep(random.uniform(3.0, 5.0))
        self._check_for_errors()
        return False

    def _unfollow_company(self) -> None:
        try:
            follow_checkbox = self.driver.find_element(
                By.XPATH, "//label[contains(.,'to stay up to date with their page.')]")
            follow_checkbox.click()
        except Exception:
            pass

    def _check_for_errors(self) -> None:
        error_elements = self.driver.find_elements(By.CLASS_NAME, 'artdeco-inline-feedback--error')
        if error_elements:
            raise Exception(f"Failed answering or file upload. {str([e.text for e in error_elements])}")

    def _discard_application(self) -> None:
        try:
            self.driver.find_element(By.CLASS_NAME, 'artdeco-modal__dismiss').click()
            time.sleep(random.uniform(3, 5))
            self.driver.find_elements(By.CLASS_NAME, 'artdeco-modal__confirm-dialog-btn')[0].click()
            time.sleep(random.uniform(3, 5))
        except Exception:
            pass

    def fill_up(self, job) -> None:
        easy_apply_content = self.driver.find_element(By.CLASS_NAME, 'jobs-easy-apply-content')
        pb4_elements = easy_apply_content.find_elements(By.CLASS_NAME, 'pb4')
        for element in pb4_elements:
            self._process_form_element(element, job)

    def _process_form_element(self, element: WebElement, job: Any) -> None:
        self._fill_additional_questions()

    def _create_and_upload_cover_letter(self, element: WebElement) -> None:
        cover_letter = self.gpt_answerer.answer_question_textual_wide_range("Write a cover letter")
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf_file:
            letter_path = temp_pdf_file.name
            c = canvas.Canvas(letter_path, pagesize=letter)
            _, height = letter
            text_object = c.beginText(100, height - 100)
            text_object.setFont("Helvetica", 12)
            text_object.textLines(cover_letter)
            c.drawText(text_object)
            c.save()
            element.send_keys(letter_path)

    def _fill_additional_questions(self) -> None:
        form_sections = self.driver.find_elements(By.CLASS_NAME, 'jobs-easy-apply-form-section__grouping')
        for section in form_sections:
            self._process_form_section(section)

    def _process_form_section(self, section: WebElement) -> None:
        if self._handle_terms_of_service(section):
            return
        if self._find_and_handle_radio_question(section):
            return
        if self._find_and_handle_textbox_question(section):
            return
        if self._find_and_handle_date_question(section):
            return
        if self._find_and_handle_dropdown_question(section):
            return

    def _handle_terms_of_service(self, element: WebElement) -> bool:
        checkbox = element.find_elements(By.TAG_NAME, 'label')
        if checkbox and any(term in checkbox[0].text.lower() for term in ['terms of service', 'privacy policy', 'terms of use']):
            checkbox[0].click()
            return True
        return False

    def _find_and_handle_radio_question(self, section: WebElement) -> bool:
        question = section.find_element(By.CLASS_NAME, 'jobs-easy-apply-form-element')
        radios = question.find_elements(By.CLASS_NAME, 'fb-text-selectable__option')
        if radios:
            question_text = section.text.lower()
            options = [radio.text.lower() for radio in radios]

            existing_answer = next((item for item in self.all_data
                                    if self._sanitize_text(question_text) in item['question'] and item['type'] == 'radio'), None)
            if existing_answer:
                self._select_radio(radios, existing_answer['answer'])
                return True

            answer = self.gpt_answerer.answer_question_textual_wide_range(question_text)
            self._select_radio(radios, answer)
            return True
        return False

    def _find_and_handle_textbox_question(self, section: WebElement) -> bool:
        textbox = section.find_elements(By.CLASS_NAME, 'jobs-easy-apply-form-element')
        if textbox:
            question_text = section.text.lower()
            existing_answer = next((item for item in self.all_data
                                    if self._sanitize_text(question_text) in item['question'] and item['type'] == 'textbox'), None)
            if existing_answer:
                textbox[0].send_keys(existing_answer['answer'])
                return True

            answer = self.gpt_answerer.answer_question_textual_wide_range(question_text)
            textbox[0].send_keys(answer)
            return True
        return False

    def _find_and_handle_date_question(self, section: WebElement) -> bool:
        date_field = section.find_elements(By.CLASS_NAME, 'artdeco-text-input')
        if date_field:
            date_text = self._get_date_text()
            date_field[0].send_keys(date_text)
            return True
        return False

    def _find_and_handle_dropdown_question(self, section: WebElement) -> bool:
        dropdown = section.find_elements(By.CLASS_NAME, 'artdeco-dropdown')
        if dropdown:
            select = Select(dropdown[0])
            options = [opt.text.lower() for opt in select.options]
            question_text = section.text.lower()
            existing_answer = next((item for item in self.all_data
                                    if self._sanitize_text(question_text) in item['question'] and item['type'] == 'dropdown'), None)
            if existing_answer:
                select.select_by_visible_text(existing_answer['answer'])
                return True

            answer = self.gpt_answerer.answer_question_textual_wide_range(question_text)
            select.select_by_visible_text(answer)
            return True
        return False

    def _select_radio(self, radios: List[WebElement], answer: str) -> None:
        for radio in radios:
            if answer.lower() in radio.text.lower():
                radio.click()
                return

    def _sanitize_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

    def _get_date_text(self) -> str:
        return date.today().strftime("%m/%d/%Y")
