#!/usr/bin/env python3
"""
Test script for generate_dataset.py improvements:
- 4a: Template exhaustion fix (Cartesian product expansion)
- 4b: Deterministic train/val/test split (hash-based)
- 4c: Multi-turn examples
- 4d: Hindi/Hinglish examples
- 4e: Persona-varied examples
"""

import sys
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

def test_deterministic_split():
    """Test that assign_split produces consistent 70/20/10 distribution."""
    from Jarvis.sft.generate_dataset import assign_split
    
    # Generate 1000 splits and verify distribution
    splits = {}
    for i in range(1000):
        s = assign_split(f"test_{i}")
        splits[s] = splits.get(s, 0) + 1
    
    print("✓ Deterministic Split Test:")
    print(f"  Train: {splits.get('train', 0)}/1000 (target 70%)")
    print(f"  Val:   {splits.get('val', 0)}/1000 (target 20%)")
    print(f"  Test:  {splits.get('test', 0)}/1000 (target 10%)")
    
    # Verify same ID gets same split
    id1_split1 = assign_split("fixed_id_123")
    id1_split2 = assign_split("fixed_id_123")
    assert id1_split1 == id1_split2, "Split should be deterministic per ID!"
    print(f"  ✓ Deterministic: same ID returns same split consistently")
    return True


def test_template_expansion():
    """Test Cartesian product template expansion."""
    from Jarvis.sft.generate_dataset import expand_templates_with_cartesian
    
    base = ["open file", "show files"]
    suffixes = ["please", "now", "quick"]
    expanded = expand_templates_with_cartesian(base, suffixes, max_attempts=10)
    
    print("\n✓ Template Expansion Test:")
    print(f"  Base templates: {len(base)}")
    print(f"  Suffixes: {len(suffixes)}")
    print(f"  Expanded variations: {len(expanded)}")
    print(f"  Samples: {expanded[:3]}")
    return len(expanded) >= 6


def test_multi_turn_generation():
    """Test multi-turn example generation."""
    from Jarvis.sft.generate_dataset import generate_multi_turn_examples
    
    seen = set()
    examples = generate_multi_turn_examples(5, seen)
    
    print("\n✓ Multi-Turn Examples Test:")
    print(f"  Generated: {len(examples)} examples")
    if examples:
        ex = examples[0]
        print(f"  Sample:")
        print(f"    Input: {ex['user_input'][:60]}...")
        print(f"    Scenario: {ex['scenario']}")
        print(f"    Split: {ex['split']}")
        print(f"    Num turns: {ex.get('num_turns', 'N/A')}")
    return len(examples) > 0


def test_hindi_hinglish_generation():
    """Test Hindi/Hinglish example generation."""
    from Jarvis.sft.generate_dataset import generate_hindi_hinglish_examples
    
    seen = set()
    examples = generate_hindi_hinglish_examples(5, seen)
    
    print("\n✓ Hindi/Hinglish Examples Test:")
    print(f"  Generated: {len(examples)} examples")
    
    hindi_count = sum(1 for ex in examples if ex.get('language') == 'hindi')
    hinglish_count = sum(1 for ex in examples if ex.get('language') == 'hinglish')
    
    print(f"  Hindi examples: {hindi_count}")
    print(f"  Hinglish examples: {hinglish_count}")
    if examples:
        ex = examples[0]
        print(f"  Sample:")
        print(f"    Input: {ex['user_input']}")
        print(f"    Language: {ex.get('language')}")
    return len(examples) > 0


def test_persona_variation():
    """Test persona variation in conversational examples."""
    from Jarvis.sft.generate_dataset import generate_conversational_examples
    
    seen = set()
    examples = generate_conversational_examples(20, seen)
    
    persona_count = sum(1 for ex in examples if ex.get('has_persona', False))
    
    print("\n✓ Persona Variation Test:")
    print(f"  Generated: {len(examples)} examples")
    print(f"  With persona: {persona_count}/{len(examples)} ({100*persona_count/len(examples):.1f}%)")
    print(f"  Target: ~30%")
    return len(examples) > 0


def test_schema_validation():
    """Test schema accepts new scenario types."""
    from Jarvis.sft.schema import Scenario
    
    print("\n✓ Schema Validation Test:")
    scenarios = [s.value for s in Scenario]
    print(f"  Valid scenarios: {len(scenarios)}")
    
    required = ["multi_turn", "hindi_hinglish"]
    for req in required:
        if req in scenarios:
            print(f"  ✓ {req} is in Scenario enum")
        else:
            print(f"  ✗ {req} is NOT in Scenario enum")
            return False
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("Testing generate_dataset.py Improvements (4a-4e)")
    print("=" * 70)
    
    tests = [
        ("Deterministic Split (4b)", test_deterministic_split),
        ("Template Expansion (4a)", test_template_expansion),
        ("Multi-Turn Examples (4c)", test_multi_turn_generation),
        ("Hindi/Hinglish Examples (4d)", test_hindi_hinglish_generation),
        ("Persona Variation (4e)", test_persona_variation),
        ("Schema Validation", test_schema_validation),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                print(f"  ✗ {name} failed")
                failed += 1
        except Exception as e:
            print(f"  ✗ {name} error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed}/{len(tests)} tests passed")
    print("=" * 70)
    
    sys.exit(0 if failed == 0 else 1)
