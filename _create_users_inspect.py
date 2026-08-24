import database
import inspect

print("funcs:", [x for x in dir(database) if any(k in x.lower() for k in ("user", "pass", "hash"))])
print("add_user sig:", inspect.signature(database.add_user))
print(inspect.getsource(database.add_user))
if hasattr(database, "change_user_password"):
    print("change_user_password sig:", inspect.signature(database.change_user_password))
    print(inspect.getsource(database.change_user_password))
else:
    print("no change_user_password")
if hasattr(database, "hash_password_secure"):
    print("hash_password_secure sig:", inspect.signature(database.hash_password_secure))
