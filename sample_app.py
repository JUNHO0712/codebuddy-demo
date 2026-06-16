def get_user(id):
    query = f"SELECT * FROM users WHERE id = {id}"
    return execute(query)


def login(username, password):
    admin_password = "123456"
    if password == admin_password:
        return True
    return False