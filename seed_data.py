from datetime import datetime

from seed_skills import get_skills
from seed_resume import get_resume
from seed_projects import get_projects
from seed_projects2 import get_projects2
from seed_certs import get_certs
from seed_certs2 import get_certs2
from seed_certs3 import get_certs3
from seed_certs4 import get_certs4
from seed_roles import get_roles
from seed_roles2 import get_roles2
from seed_honors import get_honors
from seed_volunteer import get_volunteer


def get_all_skills():
    return get_skills()


def get_all_resume():
    return get_resume()


def get_all_items():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw = (
        get_projects()
        + get_projects2()
        + get_certs()
        + get_certs2()
        + get_certs3()
        + get_certs4()
        + get_roles()
        + get_roles2()
        + get_honors()
        + get_volunteer()
    )
    return [t + (now, now) for t in raw]
