"""
Credential Manager Utility (Setup.py)

This script provides functionality to securely store, retrieve, and delete credentials 
(e.g., usernames and passwords) using the system's keyring backend. It presents a simple 
menu interface allowing users to interactively manage credentials for different services.

Features:
- Store credentials (service name, username, password) securely.
- Retrieve stored credentials (currently used internally).
- Delete credentials from the system keyring.
- Simple CLI menu interface for ease of use.

Dependencies:
- keyring (must be installed via pip)
- View.Menu.setup_credentials_menu (custom menu setup module)
"""

import keyring
from keyring.errors import PasswordDeleteError
import os
import logging
import msvcrt
from getpass import getpass
from View.Menu import setup_credentials_menu
from Controller.Logging_Controller import finish_logging
from Config import SERVICE_NAME

# Function to attempt fetch password from Windows Credentials
def fetch_password(log_start_time, SERVICE_NAME, USERNAME):
    STATUS, USER_PASSWORD = get_credentials(SERVICE_NAME, USERNAME)
    if STATUS == False:
        finish_logging(log_start_time)
        exit(1)
    return USER_PASSWORD

def store_credentials(service_name, username, new_password):
    # Store the new credentials
    keyring.set_password(service_name, username, new_password)
    print(f"[Success]✅ Credentials for '{service_name}' with username '{username}' successfully stored.")

def get_credentials(service_name, username):
    password = keyring.get_password(service_name, username)
    if password is None:
        logging.error(f"Credentials not found for '{service_name}' with username '{username}' in the Credential Manager.")
        return False, None
    else:
        return True, password

def delete_credentials(service_name, username):
    try:
        keyring.delete_password(service_name, username)
        print(f"[Success]✅ Credentials for '{service_name}' with username '{username}' have been deleted.")
    except PasswordDeleteError:
        print(f"[Error]❌ Credentials for '{service_name}' with username '{username}' not found. Failed to delete.")

def get_password(prompt='[Input] Enter password: '):
    print(prompt, end='', flush=True)
    password = ''
    while True:
        char = msvcrt.getch()
        if char in {b'\r', b'\n'}:  # Enter key
            print('')
            break
        elif char == b'\x08':  # Backspace
            if password:
                password = password[:-1]
                print('\b \b', end='', flush=True)
        elif char == b'\x03':  # Ctrl+C
            raise KeyboardInterrupt
        else:
            password += char.decode('utf-8')
            print('*', end='', flush=True)
    return password

# Setup menu
def main():
    os.system('cls')
    setup_credentials_menu()
    user_input = 0
    while(user_input != 3):
        user_input = int(input("[Input] Enter your choice [1-3]: "))
        if user_input == 1:
            print("\n")
            username = input("[Input] Enter username: ")
            password = get_password()
            store_credentials(SERVICE_NAME, username, password)
            input("\nPress enter to continue...")
            os.system('cls')
            setup_credentials_menu()
        elif user_input == 2:
            print("\n")
            username = input("[Input] Enter username: ")
            delete_credentials(SERVICE_NAME, username)
            input("\nPress enter to continue...")
            os.system('cls')
            setup_credentials_menu()
        else:
            print("\n")
            print("Invalid choice")

if __name__ == "__main__":
    main()