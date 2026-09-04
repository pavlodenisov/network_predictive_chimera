from __future__ import annotations

from intelligence.ingestion.adapters.base import RawObservationDraft
from intelligence.ingestion.dedupe import content_hash, story_cluster_key


def test_content_hash_is_stable_and_order_independent() -> None:
    a = RawObservationDraft(
        provider_record_id="x",
        content_type="news_article",
        subject_hint="Sarah Chen",
        raw_json={"b": 2, "a": 1},
        raw_text="hello",
    )
    b = RawObservationDraft(
        provider_record_id="different-id-same-content",
        content_type="news_article",
        subject_hint="Sarah Chen",
        raw_json={"a": 1, "b": 2},
        raw_text="hello",
    )
    assert content_hash(a) == content_hash(b)

    c = RawObservationDraft(
        provider_record_id="x",
        content_type="news_article",
        subject_hint="Sarah Chen",
        raw_json={"a": 1, "b": 3},
        raw_text="hello",
    )
    assert content_hash(a) != content_hash(c)


def test_story_cluster_key_groups_syndicated_titles() -> None:
    k1 = story_cluster_key("Synthetic AI Labs raises $40M Series B for inference platform")
    k2 = story_cluster_key("Inference platform: Synthetic AI Labs raises $40M in Series B round")
    k3 = story_cluster_key("Robotics startup Foundry announces new gripper hardware")
    assert k1 == k2
    assert k1 != k3
