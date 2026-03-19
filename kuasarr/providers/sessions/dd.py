# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import base64
import pickle

import requests

from kuasarr.providers.log import info


def create_and_persist_session(shared_state):
    dd = shared_state.values["config"]("Hostnames").get("dd")

    dd_session = requests.Session()

    cookies = {}
    headers = {
        'User-Agent': shared_state.values["user_agent"],
    }

    data = {
        'username': shared_state.values["config"]("DD").get("user"),
        'password': shared_state.values["config"]("DD").get("password"),
        'ajax': 'true',
        'Login': 'true',
    }

    dd_response = dd_session.post(f'https://{dd}/index/index',
                                  cookies=cookies, headers=headers, data=data, timeout=10)

    error = False
    if dd_response.status_code == 200:
        try:
            response_data = dd_response.json()
            if not response_data.get('loggedin'):
                info("DD rejected login.")
                raise ValueError
            session_id = dd_response.cookies.get("PHPSESSID")
            if session_id:
                dd_session.cookies.set('PHPSESSID', session_id, domain=dd)
            else:
                info("Invalid DD response on login.")
                error = True
        except ValueError:
            info("Could not parse DD response on login.")
            error = True

        if error:
            shared_state.values["config"]("DD").save("user", "")
            shared_state.values["config"]("DD").save("password", "")
            return None

        serialized_session = pickle.dumps(dd_session)
        session_string = base64.b64encode(serialized_session).decode('utf-8')
        shared_state.values["database"]("sessions").update_store("dd", session_string)
        return dd_session
    else:
        info("Could not create DD session")
        return None


def retrieve_and_validate_session(shared_state):
    session_string = shared_state.values["database"]("sessions").retrieve("dd")
    if not session_string:
        dd_session = create_and_persist_session(shared_state)
    else:
        try:
            serialized_session = base64.b64decode(session_string.encode('utf-8'))
            dd_session = pickle.loads(serialized_session)
            if not isinstance(dd_session, requests.Session):
                raise ValueError("Retrieved object is not a valid requests.Session instance.")
        except Exception as e:
            info(f"Session retrieval failed: {e}")
            dd_session = create_and_persist_session(shared_state)

    return dd_session



