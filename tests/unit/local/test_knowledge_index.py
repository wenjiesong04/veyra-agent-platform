import socket

import pytest

from veyra_agent_platform.local.projects.knowledge_index import build_index, retrieve


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", denied)


def test_stable_chunks_and_lexical_ranking():
    text = "The acceptance marker is ORBIT-731.\n\n" + "Unrelated weather.\n" * 200
    index = build_index("knowledge@1.0.0", text)
    again = build_index("knowledge@1.0.0", text.replace("\n", "\r\n"))
    assert index.chunks == again.chunks
    assert len(index.chunks) > 1
    hits = retrieve([index], "What is the acceptance marker?")
    assert "ORBIT-731" in hits[0].text
    assert hits[0].line_start == 1
    assert hits == retrieve([index], "What is the acceptance marker?")
    assert retrieve([index], "xyzzy") == []
    assert (
        build_index("knowledge@1.0.0", text + "changed").source_file_hash
        != index.source_file_hash
    )


def test_chinese_and_ties():
    index = build_index(
        "knowledge@1.0.0", "毕业设计题目是人工智能影视分镜生成系统\n\n天气晴朗"
    )
    hits = retrieve([index], "毕业设计题目是什么")
    assert hits and "人工智能" in hits[0].text
    other = build_index("another@1.0.0", "毕业设计题目是人工智能影视分镜生成系统")
    assert retrieve([index, other], "毕业设计") == retrieve([other, index], "毕业设计")


def test_long_lines_are_bounded_and_have_real_locators():
    index = build_index("knowledge@1.0.0", "界" * 6000)
    assert len(index.chunks) == 3
    assert all(len(chunk.text) <= 2000 for chunk in index.chunks)
    assert all(chunk.line_start == chunk.line_end == 1 for chunk in index.chunks)
    assert len({chunk.chunk_id for chunk in index.chunks}) == 3


def test_normalization_locators_scores_and_limits():
    text = "Cafe\u0301 marker\nsecond line\n\n\nweather\n\nmarker"
    index = build_index("a@1.0.0", text)
    normalized = build_index("a@1.0.0", text.replace("Cafe\u0301", "Café"))
    assert index.chunks == normalized.chunks
    assert [(c.line_start, c.line_end, c.chunk_index) for c in index.chunks] == [
        (1, 2, 0),
        (5, 5, 1),
        (7, 7, 2),
    ]
    hits = retrieve([index], "marker")
    assert [h.chunk_index for h in hits] == [0, 2]
    assert [h.score for h in hits] == [5, 5]
    assert [h.rank for h in hits] == [1, 2]
    assert retrieve([index], "marker", top_k=1) == hits[:1]
    for query in ("", " \n", "!!!", "xyzzy"):
        assert retrieve([index], query) == []
    assert build_index("a@1.0.0", "\n ").chunks == ()
    with pytest.raises(ValueError, match="source_file_hash"):
        build_index("a@1.0.0", text, "0" * 64)


def test_top_k_is_global_and_does_not_fill_with_zero_scores():
    first = build_index("a@1.0.0", "\n\n".join(["marker " + str(i) for i in range(9)]))
    second = build_index("b@1.0.0", "marker question exact\n\nweather")
    hits = retrieve([first, second], "marker question exact")
    assert len(hits) == 6
    assert hits[0].knowledge_ref == "b@1.0.0"
    assert hits[0].score == 7
    assert [h.chunk_index for h in hits[1:]] == list(range(5))
    assert retrieve([first, second], "question") == retrieve([second], "question")
