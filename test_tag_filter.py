
from Jarvis.core.orchestrator import _TagStreamFilter

def test_tag_filter_basic():
    f = _TagStreamFilter()
    tokens = ["Hello ", "[SHELL]", "ls", " -la", "[/SHELL]", " world"]
    display = ""
    for t in tokens:
        display += f.feed(t)
    display += f.flush()
    
    assert display == "Hello  world"
    assert f.shell_commands == ["ls -la"]
    print("Basic test passed!")

def test_tag_filter_split_tags():
    f = _TagStreamFilter()
    tokens = ["Open ", "[ACT", "ION]", "launch_app: notepad", "[/ACT", "ION]", "!"]
    display = ""
    for t in tokens:
        display += f.feed(t)
    display += f.flush()
    
    # Note: The filter might leave some spaces or handle things differently depending on how it's written.
    # Current implementation:
    # [ACTION] is found in buf_upper. display += self._buf[:idx] (which is "Open ")
    # Then it switches to _in_tag.
    assert display == "Open !"
    assert f.action_commands == ["launch_app: notepad"]
    print("Split tags test passed!")

def test_tag_filter_mixed():
    f = _TagStreamFilter()
    text = "Sure thing! [SHELL]echo hi[/SHELL] [ACTION]launch_app: calc[/ACTION] Done."
    # Feed character by character to simulate extreme streaming
    display = ""
    for ch in text:
        display += f.feed(ch)
    display += f.flush()
    
    assert "Sure thing!" in display
    assert "Done." in display
    assert "[SHELL]" not in display
    assert "[ACTION]" not in display
    assert f.shell_commands == ["echo hi"]
    assert f.action_commands == ["launch_app: calc"]
    print("Mixed test passed!")

if __name__ == "__main__":
    test_tag_filter_basic()
    test_tag_filter_split_tags()
    test_tag_filter_mixed()
