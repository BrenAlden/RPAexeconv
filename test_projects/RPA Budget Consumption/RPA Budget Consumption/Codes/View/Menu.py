import os

version = "1.1"

def cmd_top_logo():
    os.system('cls')
    print("""
   ##########\    ## \   ###########\\
 ##### ______/    ## |       ##  ___/
####  /           ## |       ## |
####  \           ## |       ## |
\ ############    ## |       ## |
 \___________/    \__|       \__|
""")
    
def power_console_menu():
    print(f"Power Console v{version}")
    print("============================")
    print("1. Start Program")
    print("2. Install Dependencies")
    print("3. Setup Credentials")
    print("4. Exit")

def setup_credentials_menu():
    os.system('cls')
    print("Credentials setup menu")
    print("============================")
    print("1. Insert new credentials")
    print("2. Delete credentials")
    print("3. Back")

if __name__ == "__main__":
   cmd_top_logo()
   power_console_menu()
