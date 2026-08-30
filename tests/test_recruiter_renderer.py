def test_rendercv_runtime_is_importable():
    import rendercv
    import typst

    assert rendercv is not None
    assert typst is not None
