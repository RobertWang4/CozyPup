"""Turn the live Cloud Run service spec into a two-container spec (backend + clf sidecar).

    gcloud run services describe backend --region R --format=json > svc.json
    python3 nano/serve/patch_service.py svc.json BACKEND_IMAGE CLF_IMAGE > new.json
    gcloud run services replace new.json --region R

Why not `gcloud run deploy --container ...`: the existing container is unnamed, so
`--container=backend` ADDED a second ingress container instead of updating it and Cloud
Run rejected the revision ("exactly one container with an exposed port"). Editing the
spec keeps every env var / secret exactly as deployed and only touches what we mean to.
"""
import json, sys

CLF = {
    "name": "clf",
    # 2 vCPU: with 1 vCPU the 84-token prompt took ~280 ms on Cloud Run, right at the timeout
    "resources": {"limits": {"cpu": "2", "memory": "1Gi"}},
    "startupProbe": {
        "httpGet": {"path": "/health", "port": 8081},
        "initialDelaySeconds": 2, "periodSeconds": 2, "timeoutSeconds": 2, "failureThreshold": 60,
    },
}

svc = json.load(open(sys.argv[1]))
backend_image, clf_image = sys.argv[2], sys.argv[3]

# strip server-generated fields; `replace` creates a fresh revision
svc.pop("status", None)
svc["metadata"] = {k: v for k, v in svc["metadata"].items() if k in ("name", "namespace", "labels", "annotations")}
svc["metadata"].get("annotations", {}).pop("run.googleapis.com/operation-id", None)
tmpl = svc["spec"]["template"]
tmpl.setdefault("metadata", {}).pop("name", None)

containers = tmpl["spec"]["containers"]
backend = next((c for c in containers if c.get("name") in (None, "backend")), containers[0])
backend["name"] = "backend"
backend["image"] = backend_image
BACKEND_ENV = {"EMERGENCY_CLF_URL": "http://127.0.0.1:8081", "EMERGENCY_CLF_TIMEOUT_MS": "800"}
env = [e for e in backend.get("env", []) if e.get("name") not in BACKEND_ENV]
env.extend({"name": k, "value": v} for k, v in BACKEND_ENV.items())
backend["env"] = env

clf = dict(CLF, image=clf_image)
tmpl["spec"]["containers"] = [backend, clf]
# backend waits for clf's startup probe before it is started
tmpl["metadata"].setdefault("annotations", {})["run.googleapis.com/container-dependencies"] = json.dumps({"backend": ["clf"]})

json.dump(svc, sys.stdout, indent=1)
