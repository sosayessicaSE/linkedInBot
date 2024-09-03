import logging
from typing import Any
class LinkedInBotState:
    def __init__(self):
        self.reset()

    def reset(self):
        """Reset the state of the bot."""
        self.credentials_set = False
        self.api_key_set = False
        self.gpt_answerer_set = False
        self.parameters_set = False
        self.logged_in = False
        self.job_application_profile_set = True

    def validate_state(self, required_keys):
        """
        Validate the current state against required keys.

        Args:
            required_keys (list): A list of state attributes that must be set.

        Raises:
            ValueError: If any of the required keys are not set.
        """
        for key in required_keys:
            if not getattr(self, key):
                raise ValueError(f"{key.replace('_', ' ').capitalize()} must be set before proceeding.")
        

class LinkedInBotFacade:
    def __init__(self, login_component, apply_component):
        self.login_component = login_component
        self.apply_component = apply_component
        self.state = LinkedInBotState()
        self.job_application_profile = None
        self.email = None
        self.password = None
        self.parameters = None

    def set_job_application_profile(self, job_application_profile):
        self._validate_non_empty(job_application_profile, "Job application profile")
        self.job_application_profile = job_application_profile
        self.state.job_application_profile_set = True  # Update the state
        logging.info("Job application profile set.")


    def set_secrets(self, email, password):
        self._validate_non_empty(email, "Email")
        self._validate_non_empty(password, "Password")
        self.email = email
        self.password = password
        self.state.credentials_set = True
        logging.info("Credentials set.")

    def set_gpt_answerer_and_resume_generator(self, gpt_answerer_component: Any) -> None:
   
        # Check if the job application profile is set
        if not self.state.job_application_profile_set:
            raise ValueError("Job application profile must be set before proceeding.")
        
        # Ensure the GPT answerer component has the 'set_job_application_profile' method
        if not hasattr(gpt_answerer_component, 'set_job_application_profile'):
            raise AttributeError("GPT answerer component does not have the 'set_job_application_profile' method.")
        
        # Set the job application profile in the GPT answerer component
        gpt_answerer_component.set_job_application_profile(self.job_application_profile)
        
        # Set the GPT answerer in the apply component
        self.apply_component.set_gpt_answerer(gpt_answerer_component)
        
        # Update state and log the action
        self.state.gpt_answerer_set = True
        logging.info("GPT answerer and resume generator set.")

    def set_parameters(self, parameters):
        self._validate_non_empty(parameters, "Parameters")
        self.parameters = parameters
        self.apply_component.set_parameters(parameters)
        self.state.parameters_set = True
        logging.info("Parameters set.")

    def start_login(self):
        try:
            self.state.validate_state(['credentials_set'])
            logging.debug(f"Attempting login with email: {self.email}")
            self.login_component.set_secrets(self.email, self.password)
            self.login_component.start()
            self.state.logged_in = True
            logging.info("Login process started and completed.")
        except Exception as e:
            logging.error(f"An error occurred during login: {e}")

    def start_apply(self):
        try:
            logging.debug(f"Current state before applying: {vars(self.state)}")
            self.state.validate_state(['logged_in', 'job_application_profile_set', 'gpt_answerer_set', 'parameters_set'])
            logging.debug(f"Applying with profile: {self.job_application_profile}")
            self.apply_component.start_applying()
            logging.info("Job application process started.")
        except Exception as e:
            logging.error(f"An error occurred during application: {e}")

    def _validate_non_empty(self, value, name):
        if not value:
            raise ValueError(f"{name} cannot be empty.")
