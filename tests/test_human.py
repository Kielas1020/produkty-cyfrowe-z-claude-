"""Testy ludzkiego tempa: losowość, limity akcji, pisanie, ruch myszy."""

from __future__ import annotations

import random

import pytest

from kdp_publisher.human import HumanActor, Pacer, PacingProfile


def test_presets_differ_and_are_ordered():
    fast = PacingProfile.preset("fast")
    normal = PacingProfile.preset("normal")
    paranoid = PacingProfile.preset("paranoid")
    assert fast.action_max_s < normal.action_max_s < paranoid.action_max_s
    assert paranoid.max_actions_per_minute < normal.max_actions_per_minute
    with pytest.raises(ValueError, match="Nieznany profil"):
        PacingProfile.preset("turbo")


def test_delays_are_random_within_bounds(sleep_calls: list[float]):
    profile = PacingProfile(action_min_s=0.5, action_max_s=1.0, max_actions_per_minute=None)
    pacer = Pacer(profile, rng=random.Random(1), sleep=sleep_calls.append)
    for _ in range(30):
        pacer.between_actions()
    assert len(sleep_calls) == 30
    assert all(0.5 <= value <= 1.0 for value in sleep_calls)
    assert len(set(sleep_calls)) > 25  # praktycznie każda pauza inna


def test_typing_delay_is_random_and_in_range():
    profile = PacingProfile(typing_min_ms=40, typing_max_ms=160, max_actions_per_minute=None)
    pacer = Pacer(profile, rng=random.Random(3), sleep=lambda _: None)
    delays = {pacer.typing_delay_ms() for _ in range(100)}
    assert delays
    assert all(40 <= value <= 160 for value in delays)
    assert len(delays) > 30


def test_token_bucket_throttles(sleep_calls: list[float]):
    profile = PacingProfile(
        action_min_s=0.0, action_max_s=0.0, max_actions_per_minute=10.0
    )
    pacer = Pacer(profile, rng=random.Random(5), sleep=sleep_calls.append)
    # 25 akcji „na raz” przy limicie 10/min: token bucket musi dociążyć pauzami.
    for _ in range(25):
        pacer.between_actions()
    assert sleep_calls, "Token bucket powinien wstrzymywać nadmiar akcji"
    assert sum(sleep_calls) > 0


def test_no_limit_means_no_extra_sleep(sleep_calls: list[float]):
    profile = PacingProfile(action_min_s=0.0, action_max_s=0.0, max_actions_per_minute=None)
    pacer = Pacer(profile, rng=random.Random(5), sleep=sleep_calls.append)
    for _ in range(50):
        pacer.between_actions()
    assert sleep_calls == []


def test_scaled_profile():
    profile = PacingProfile.preset("normal").scaled(0.5)
    assert profile.action_min_s == pytest.approx(PacingProfile().action_min_s * 0.5)


def test_actor_types_text_in_chunks(kdp_page, pacer):
    from fakes import FakeLocator

    actor = HumanActor(kdp_page, pacer)
    target = kdp_page.get_by_label("Book title")
    assert isinstance(target, FakeLocator)
    actor.type_text(target, "Notatnik w kropki 120 stron", label="title")
    element = kdp_page.by_id("data-print-book-title")
    assert element.value == "Notatnik w kropki 120 stron"
    assert len(element.typed) > 1  # wpisywane partiami, nie jednym strzałem


def test_actor_clears_before_typing(kdp_page, pacer):
    actor = HumanActor(kdp_page, pacer)
    target = kdp_page.get_by_label("Book title")
    target.fill("stare dane")
    actor.type_text(target, "nowe dane")
    assert kdp_page.by_id("data-print-book-title").value == "nowe dane"


def test_actor_click_moves_mouse_first(kdp_page, pacer):
    actor = HumanActor(kdp_page, pacer)
    target = kdp_page.get_by_role("button", name="Save as draft")
    actor.click(target, label="save")
    assert kdp_page.mouse_moves > 5, "Mysz powinna przejechać po krzywej, nie teleportować się"
    assert target.first._elements[0].clicks == 1


def test_actor_select_option_falls_back_to_text(kdp_page, pacer):
    """Element <select>: wartość trafia do pola (opcjonalnie z fallbackiem na klik w tekst)."""
    actor = HumanActor(kdp_page, pacer)
    target = kdp_page.get_by_label("Language")
    actor.select_option(target, "Polish")
    assert kdp_page.by_id("data-print-book-language").value == "Polish"
