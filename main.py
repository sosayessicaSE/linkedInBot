import os
import re
import sys
import logging
from pathlib import Path
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from src.utils import chromeBrowserOptions
from src.gpt import GPTAnswerer
from src.linkedIn_authenticator import LinkedInAuthenticator
from src.linkedIn_bot_facade import LinkedInBotFacade
from src.linkedIn_job_manager import LinkedInJobManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ConfigError(Exception):
    pass

class ConfigValidator:
    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        try:
            with open(yaml_path, 'r') as stream:
                data = yaml.safe_load(stream)
                logging.debug(f"Loaded YAML data from {yaml_path}: {data}")
                return data
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"File not found: {yaml_path}")

    @staticmethod
    def validate_config(config_yaml_path: Path) -> dict:
        parameters = ConfigValidator.validate_yaml_file(config_yaml_path)
        logging.debug(f"Config parameters: {parameters}")

        # Validate required keys and types
        required_keys = {
            'remote': bool,
            'experienceLevel': dict,
            'jobTypes': dict,
            'date': dict,
            'positions': list,
            'locations': list,
            'distance': int,
            'companyBlacklist': list,
            'titleBlacklist': list
        }

        for key, expected_type in required_keys.items():
            if key not in parameters:
                if key in ['companyBlacklist', 'titleBlacklist']:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Missing or invalid key '{key}' in config file {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                if key in ['companyBlacklist', 'titleBlacklist'] and parameters[key] is None:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Invalid type for key '{key}' in config file {config_yaml_path}. Expected {expected_type}.")

        experience_levels = ['internship', 'entry', 'associate', 'mid-senior level', 'director', 'executive']
        for level in experience_levels:
            if not isinstance(parameters['experienceLevel'].get(level), bool):
                raise ConfigError(f"Experience level '{level}' must be a boolean in config file {config_yaml_path}")

        job_types = ['full-time', 'contract', 'part-time', 'temporary', 'internship', 'other', 'volunteer']
        for job_type in job_types:
            if not isinstance(parameters['jobTypes'].get(job_type), bool):
                raise ConfigError(f"Job type '{job_type}' must be a boolean in config file {config_yaml_path}")

        date_filters = ['all time', 'month', 'week', '24 hours']
        for date_filter in date_filters:
            if not isinstance(parameters['date'].get(date_filter), bool):
                raise ConfigError(f"Date filter '{date_filter}' must be a boolean in config file {config_yaml_path}")

        if not all(isinstance(pos, str) for pos in parameters['positions']):
            raise ConfigError(f"'positions' must be a list of strings in config file {config_yaml_path}")
        if not all(isinstance(loc, str) for loc in parameters['locations']):
            raise ConfigError(f"'locations' must be a list of strings in config file {config_yaml_path}")

        approved_distances = {0, 5, 10, 25, 50, 100}
        if parameters['distance'] not in approved_distances:
            raise ConfigError(f"Invalid distance value in config file {config_yaml_path}. Must be one of: {approved_distances}")

        for blacklist in ['companyBlacklist', 'titleBlacklist']:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(f"'{blacklist}' must be a list in config file {config_yaml_path}")
            if parameters[blacklist] is None:
                parameters[blacklist] = []

        return parameters

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> tuple:
        secrets = ConfigValidator.validate_yaml_file(secrets_yaml_path)
        logging.debug(f"Secrets parameters: {secrets}")

        mandatory_secrets = ['email', 'password', 'openai_api_key']

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(f"Missing secret '{secret}' in file {secrets_yaml_path}")

        if not ConfigValidator.validate_email(secrets['email']):
            raise ConfigError(f"Invalid email format in secrets file {secrets_yaml_path}.")
        if not secrets['password']:
            raise ConfigError(f"Password cannot be empty in secrets file {secrets_yaml_path}.")
        if not secrets['openai_api_key']:
            raise ConfigError(f"OpenAI API key cannot be empty in secrets file {secrets_yaml_path}.")

        return secrets['email'], str(secrets['password']), secrets['openai_api_key']

    @staticmethod
    def validate_email(email: str) -> bool:
        # Simple regex for validating an email address
        email_regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
        return bool(email_regex.match(email))


class FileManager:
    @staticmethod
    def find_file(name_containing: str, with_extension: str, at_path: Path) -> Path:
        return next((file for file in at_path.iterdir() if name_containing.lower() in file.name.lower() and file.suffix.lower() == with_extension.lower()), None)

    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        required_files = ['secrets.yaml', 'config.yaml']
        missing_files = [file for file in required_files if not (app_data_folder / file).exists()]
        
        if missing_files:
            raise FileNotFoundError(f"Missing files in the data folder: {', '.join(missing_files)}")

        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        return (app_data_folder / 'secrets.yaml', app_data_folder / 'config.yaml', app_data_folder )

def init_browser() -> webdriver.Chrome:
    try:
        options = chromeBrowserOptions()
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logging.error(f"Failed to initialize browser: {str(e)}")
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")

def create_and_run_bot(email: str, password: str, parameters: dict, openai_api_key: str):
    try:
        os.system('cls' if os.name == 'nt' else 'clear')

        browser = init_browser()
        login_component = LinkedInAuthenticator(browser)
        apply_component = LinkedInJobManager(browser)
        gpt_answerer_component = GPTAnswerer(openai_api_key)
        bot = LinkedInBotFacade(login_component, apply_component)
        bot.set_secrets(email, password)
        bot.set_gpt_answerer_and_resume_generator(gpt_answerer_component)
        bot.set_parameters(parameters)
        bot.start_login()
        bot.start_apply()
    except yaml.YAMLError as exc:
        logging.error(f"Error parsing YAML content: {exc}")
    except WebDriverException as e:
        logging.error(f"WebDriver error occurred: {e}")
    except Exception as e:
        logging.error(f"Error running the bot: {str(e)}")

@click.command()
@click.option('--config', default='config.yaml', help='Configuration file name.')
@click.option('--secrets', default='secrets.yaml', help='Secrets file name.')
@click.option('--data-folder', default='data_folder', help='Data folder path.')
def main(config, secrets, data_folder):
    try:
        data_folder_path = Path(data_folder)
        secrets_file, config_file, output_folder = FileManager.validate_data_folder(data_folder_path)

        parameters = ConfigValidator.validate_config(config_file)
        email, password, openai_api_key = ConfigValidator.validate_secrets(secrets_file)

        parameters['outputFileDirectory'] = output_folder

        create_and_run_bot(email, password, parameters, openai_api_key)
    except ConfigError as ce:
        logging.error(f"Configuration error: {str(ce)}")
        logging.info("Refer to the configuration guide for troubleshooting: https://github.com/feder-cr/LinkedIn_AIHawk_automatic_job_application/blob/main/readme.md#configuration")
    except FileNotFoundError as fnf:
        logging.error(f"File not found: {str(fnf)}")
    except yaml.YAMLError as ye:
        logging.error(f"YAML parsing error: {str(ye)}")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()
