# tests/test_docker_workflow.py
"""Static checks on the image workflow (.github/workflows/docker.yml).

The published image is multi-arch, and the workflow gets there without
emulation: one job per architecture, each on a runner of that architecture,
pushing its manifest by digest, followed by a merge that combines the digests
into a tagged manifest list. These tests pin that shape — a regression to
`docker/setup-qemu-action` or to a single `platforms:` list would be a silent
one (the build still succeeds, just 5-10x slower and cross-compiled).
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docker.yml"


def _load() -> dict:
    # PyYAML follows YAML 1.1, where the bare `on:` key is the boolean True.
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _build_job() -> dict:
    return _load()["jobs"]["build"]


def _steps(job: dict) -> list:
    return job["steps"]


def _uses(job: dict) -> list:
    return [str(step.get("uses", "")) for step in _steps(job)]


def _runs(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(job))


def _with(build: dict, step_name: str) -> dict:
    for step in _steps(build):
        if step.get("name") == step_name:
            return step.get("with") or {}
    raise AssertionError(f"no step named {step_name!r}")


def test_build_runs_one_job_per_architecture_on_native_runners():
    build = _build_job()
    entries = build["strategy"]["matrix"]["include"]
    pairs = {(entry["runner"], entry["platform"], entry["arch"]) for entry in entries}
    assert pairs == {
        ("ubuntu-24.04", "linux/amd64", "amd64"),
        ("ubuntu-24.04-arm", "linux/arm64", "arm64"),
    }
    assert build["runs-on"] == "${{ matrix.runner }}"
    # One failing leg must not cancel the other: the merge needs both, and a
    # cancelled sibling hides which platform is actually broken.
    assert build["strategy"]["fail-fast"] is False


def test_workflow_does_not_use_emulation():
    dumps = yaml.safe_dump(_load())
    assert "setup-qemu-action" not in dumps
    # The build must target a single platform per job — a list here means one
    # runner cross-builds the others, which is exactly what QEMU looked like.
    platforms = _with(_build_job(), "Build and push by digest")["platforms"]
    assert platforms == "${{ matrix.platform }}"


def test_build_pushes_by_digest_only():
    build = _build_job()
    outputs = _with(build, "Build and push by digest")["outputs"]
    # A digest push leaves the image unnamed; `merge` is what gives it tags.
    assert "push-by-digest=true" in outputs
    assert "push=true" in outputs
    # And pull requests must not export at all — they have no registry write.
    assert "github.event_name != 'pull_request'" in outputs
    assert _with(build, "Build and push by digest")["target"] == "allinone"


def test_each_architecture_keeps_its_own_cache_scope():
    # Both legs run at once; a shared scope has them overwrite each other.
    assert _with(_build_job(), "Build and push by digest")["cache-from"] == (
        "type=gha,scope=build-${{ matrix.arch }}"
    )


def test_merge_combines_both_digests_into_one_manifest_list():
    jobs = _load()["jobs"]
    merge = jobs["merge"]
    assert "build" in merge["needs"]
    assert "imagetools create" in _runs(merge)
    # Both legs are required by name, so a matrix that lost one fails here
    # instead of publishing an image that only breaks on arm64.
    script = _runs(merge)
    assert "for arch in amd64 arm64" in script
    # `imagetools create` reports the merged descriptor, not a bare digest.
    assert "containerimage.descriptor" in script
    # The merged manifest list — not a platform manifest — is what gets pulled.
    assert merge["outputs"]["digest"] == "${{ steps.merge.outputs.digest }}"


def test_smoke_job_starts_the_real_image():
    smoke = _load()["jobs"]["smoke"]
    assert "build" in smoke["needs"] and "merge" in smoke["needs"]
    script = _runs(smoke)
    assert "docker run -d --name proxyhub-smoke" in script
    # Every probe runs inside the container: no host port is published.
    assert "--publish" not in script and " -p " not in script
    assert "http://127.0.0.1:8000/healthz" in script
