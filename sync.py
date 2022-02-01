#!/usr/bin/env python3

import json
import requests
import os
import pprint
import sys

pp = pprint.PrettyPrinter(indent=4)

MAX_RESULTS = 5000  # This is the highest value allowed on this Jira server

env_vars = [
    "JIRA_LOCATION",
    "JIRA_USER",
    "JIRA_PASSWORD",
    "NI_LOCATION",
    "NI_USER",
    "NI_PASSWORD",
]

for v in env_vars:
    if v not in os.environ:
        print(f"Error: {v} must be defined")
        sys.exit(1)

tickets = []
i = 0
while True:
    r = requests.get(
        os.environ["JIRA_LOCATION"] + "/rest/api/2/search",
        params={
            "jql": "",
            "fields": "summary,customfield_10286,customfield_10287,customfield_10288,"
            + "customfield_10289,customfield_10290,customfield_10292,customfield_10294",
            "maxResults": MAX_RESULTS,
            "startAt": i,
        },
        auth=(os.environ["JIRA_USER"], os.environ["JIRA_PASSWORD"]),
    )
    assert r.status_code == 200
    chunk = r.json()["issues"]
    if len(chunk) == 0:
        break
    tickets += chunk
    i += MAX_RESULTS

print(f"{len(tickets)} tickets")

# fmt:off
tickets = [
    {
        "key":           t.get("key"),
        "summary":       t["fields"].get("summary"),
        "service":       t["fields"].get("customfield_10286"),
        "connection":    t["fields"].get("customfield_10287"),
        "equipment":     t["fields"].get("customfield_10288"),
        "version":       t["fields"].get("customfield_10289"),
        "site":          t["fields"].get("customfield_10290"),
        "escalated_to":  t["fields"].get("customfield_10292"),
        "affected_orgs": t["fields"].get("customfield_10294"),
    }
    for t in tickets
]
# fmt:on

# Filter out None values
tickets = [{k: v for k, v in t.items() if v is not None} for t in tickets]

# Split comma separated fields
for t in tickets:
    if "service" in t:
        t["service"] = [s.strip() for s in t["service"].split(",")]
    else:
        t["service"] = []


class NIAuth(requests.auth.AuthBase):
    def __call__(self, r):
        r.headers[
            "Authorization"
        ] = f"ApiKey {os.environ['NI_USER']}:{os.environ['NI_PASSWORD']}"
        return r


# Clear all tickets
r = requests.delete(os.environ["NI_LOCATION"] + "/api/v1/ticket/", auth=NIAuth())
assert r.status_code == 200 or r.status_code == 204

# Create tickets and relationships
for t in tickets:
    r = requests.post(
        os.environ["NI_LOCATION"] + "/api/v1/ticket/",
        auth=NIAuth(),
        json={
            "node_type": "/api/v1/node_type/ticket/",
            "node_meta_type": "Logical",
            "node": {"name": f"{t['key']}: {t['summary']}"},
        },
    )

    assert r.status_code == 201
    t_path = r.headers["Location"]
    print(t_path)

    for s in t["service"]:
        print(s, end="")

        # Get s_path of service with name s
        r = requests.get(
            os.environ["NI_LOCATION"] + "/api/v1/service/",
            auth=NIAuth(),
            params={"node_name": s},
        )

        assert r.status_code == 200

        if r.json()["meta"]["total_count"] != 1:
            print(" X")
            continue

        s_path = r.json()["objects"][0]["resource_uri"]
        print(f" {s_path}")

        # Create relationship
        r = requests.post(
            os.environ["NI_LOCATION"] + "/api/v1/relationship/",
            auth=NIAuth(),
            json={"type": "Is_about", "start": t_path, "end": s_path},
        )

        assert r.status_code == 201
