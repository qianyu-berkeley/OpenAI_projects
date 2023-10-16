from dotenv import dotenv_values


def read_credentials(secret_file):
    config = dotenv_values(secret_file)
    return config
