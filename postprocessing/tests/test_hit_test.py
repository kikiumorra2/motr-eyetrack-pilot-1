import motr_char_events as ce


def test_offsets_and_mapping():
    words = ["The", "cat", "sat", "wrapped", "on", "the", "mat."]
    off = ce.span_offsets(words)
    assert off == [0, 5, 10, 15, 24, 28, 33, 39]
    assert ce.word_length("naïve") == 5 and ce.word_length("a😀b") == 3
    for g in range(off[-1]):
        i, k = ce.word_of_global(off, g)
        assert ce.global_index(off, i, k) == g
        assert 0 <= k <= ce.word_length(words[i]) + 1
    assert ce.word_of_global(off, 38) == (6, 5)
    assert ce.char_at("The", 0) == " " and ce.char_at("The", 1) == "T" and ce.char_at("The", 4) == " "
    assert ce.span_offsets([]) == [0]


def test_shared_hit_test_fixture(js_hittest):
    """Every (x, y) → state case recorded by the JS implementation."""
    table, offsets = js_hittest["table"], js_hittest["offsets"]
    assert ce.span_offsets(js_hittest["words"]) == offsets
    index = ce.HitIndex(table)
    mismatches = [(c["x"], c["y"], c["state"], ce.hit_state(index, offsets, c["x"], c["y"]))
                  for c in js_hittest["cases"] if ce.hit_state(index, offsets, c["x"], c["y"]) != c["state"]]
    assert not mismatches, mismatches[:10]
    assert len(js_hittest["cases"]) > 400


def test_char_box_and_fake_table(js_hittest):
    table, offsets = js_hittest["table"], js_hittest["offsets"]
    assert ce.char_box(table, offsets, 0) is None            # zero-width leading space
    assert ce.char_box(table, offsets, 1) == [120, 180, 130, 201]
    t = ce.fake_table(["The", "cat"], char_w=10, line_chars=60)
    assert t["words"][0]["frags"][0]["xs"] == [120, 130, 140, 150, 160]
    assert t["block"][0] == 100


def test_tables_equal(js_hittest):
    import copy
    a = js_hittest["table"]
    b = copy.deepcopy(a)
    assert ce.tables_equal(a, b)
    b["words"][3]["frags"][1]["xs"][2] += 0.04
    assert ce.tables_equal(a, b)
    b["words"][3]["frags"][1]["xs"][2] += 0.02
    assert not ce.tables_equal(a, b)
