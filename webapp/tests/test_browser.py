"""Real Chromium tests; install the project with the dev extra to run these locally."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from script.tests.scenarios import example, scenarios

playwright = pytest.importorskip('playwright.sync_api')


@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as p:
        executable = os.environ.get('CHROME_PATH', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        try:
            instance = p.chromium.launch(
                executable_path=executable if Path(executable).exists() else None, headless=True
            )
        except Exception:
            pytest.skip('Install Chromium using python -m playwright install chromium, or set CHROME_PATH')
        yield instance
        instance.close()


def new_context(browser, **options):
    """A fresh browser profile that has already chosen Spain on the first-visit picker."""
    context = browser.new_context(**options)
    context.add_init_script(
        "try { localStorage.setItem('visafilla.country', 'ES'); localStorage.setItem('visafilla.welcome', 'hidden') }"
        ' catch (e) {}'
    )
    return context


@pytest.fixture
def page(browser, web_server):
    context = new_context(browser, viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(web_server.origin)
    page.wait_for_selector('[data-action="new"]')
    # Fictional profiles belong only to isolated browser tests.
    page.evaluate(
        """async data => {
      const {testAdapter: {state, makeProfile, render, persist}} = await import("/app.js");
      state.profiles=['alpha','bravo','charlie'].map(name=>{
        const values=structuredClone(data);values.personal.given_names=name.toUpperCase();
        const profile=makeProfile(name[0].toUpperCase()+name.slice(1),values);
        profile.id=name;return profile;
      });state.activeId='alpha';render();return persist();
    }""",
        example(),
    )
    yield page
    assert not errors, f'JavaScript errors: {errors}'
    context.close()


def menu(page, target):
    """Click an entry in the applicant menu, opening the menu first."""
    if page.locator('#applicant-menu').is_hidden():
        page.locator('#applicant-switch').click()
    page.locator(target).click()


def step(page, n):
    page.locator(f'#steps [data-step="{n}"]').click()


def choose(page, path, value):
    """Tap a choice chip."""
    page.locator(f'[data-field="{path}"][value="{value}"]').check()


def chip(page, path, value):
    return page.locator(f'[data-field="{path}"][value="{value}"]')


def field(page, path):
    return page.locator(f'[data-field="{path}"]').first


def apply_data(page, data):
    page.locator('#json-view').click()
    page.locator('#json-editor').fill(json.dumps(data, indent=2))
    page.locator('#apply-json').click()
    playwright.expect(page.locator('#json-status')).to_contain_text('JSON applied')
    page.locator('#form-view').click()


def test_profiles_autosave_reload_isolation_and_guidance(page):
    assert page.locator('.profile-button').count() == 3
    field(page, 'personal.given_names').fill('ALPHA EDITED')
    page.locator('#step-title').click()
    playwright.expect(page.locator('#save-status')).to_have_text('Saved on this device')
    page.reload()
    page.wait_for_selector('[data-profile="alpha"]', state='attached')
    playwright.expect(field(page, 'personal.given_names')).to_have_value('ALPHA EDITED')
    menu(page, '[data-profile="bravo"]')
    playwright.expect(field(page, 'personal.given_names')).to_have_value('BRAVO')
    assert page.locator('.help-tip[lang="fa"][dir="rtl"]').count() >= 10
    tip = page.locator('[data-field-wrap="personal.surname"] .help-tip')
    playwright.expect(tip).to_be_hidden()
    page.locator('[data-field-wrap="personal.surname"] .help-icon').hover()
    playwright.expect(tip).to_be_visible()
    assert field(page, 'personal.surname').get_attribute('aria-describedby') == tip.get_attribute('id')
    assert page.locator('html').get_attribute('lang') == 'en'
    playwright.expect(page.locator('#draft-banner')).to_have_count(0)
    playwright.expect(page.locator('#progress-detail')).to_contain_text('answered')


def test_only_values_the_user_did_not_enter_need_a_check(page):
    wrap = page.locator('[data-field-wrap="personal.surname"]')
    field(page, 'personal.surname').fill('NEWNAME')
    page.locator('#step-title').click()
    # Typed answers are simply answered: a tick, no confirmation step.
    playwright.expect(wrap).to_have_class(re.compile('is-ok'))
    playwright.expect(wrap.locator('.confirm-button')).to_have_count(0)
    playwright.expect(page.locator('#save-status')).to_have_text('Saved on this device')
    page.reload()
    playwright.expect(page.locator('[data-field-wrap="personal.surname"]')).to_have_class(re.compile('is-ok'))
    # Example values must be replaced and can never be confirmed.
    field(page, 'personal.surname').fill('FICTIONAL NAME')
    page.locator('#step-title').click()
    playwright.expect(wrap.locator('.field-note.example')).to_be_visible()
    playwright.expect(wrap.locator('.confirm-button')).to_have_count(0)
    # Choosing a chip answers immediately.
    choose(page, 'personal.sex', 'female')
    playwright.expect(page.locator('[data-field-wrap="personal.sex"]')).to_have_class(re.compile('is-ok'))
    playwright.expect(chip(page, 'personal.sex', 'female')).to_be_checked()
    # Imported values ask for one check, then count as answered.
    page.locator('#json-view').click()
    data = json.loads(page.locator('#json-editor').input_value())
    data['personal']['place_of_birth'] = 'SHIRAZ'
    page.locator('#json-editor').fill(json.dumps(data))
    page.locator('#apply-json').click()
    page.locator('#form-view').click()
    review = page.locator('[data-field-wrap="personal.place_of_birth"]')
    playwright.expect(review.locator('.field-note.review')).to_contain_text('Imported')
    to_check = lambda: int(re.search(r'(\d+) to check', page.locator('#progress-detail').inner_text())[1])  # noqa: E731
    before = to_check()
    review.locator('.confirm-button').click()
    playwright.expect(review).to_have_class(re.compile('is-ok'))
    assert to_check() == before - 1


def test_dates_fill_dashes_and_enter_moves_on(page):
    step(page, 4)
    field(page, 'journey.arrival_date').fill('')
    field(page, 'journey.arrival_date').press_sequentially('01062027')
    playwright.expect(field(page, 'journey.arrival_date')).to_have_value('01-06-2027')
    field(page, 'journey.arrival_date').press('Enter')
    assert page.evaluate('document.activeElement.id') == 'field-journey.departure_date'


def test_persian_guidance_keeps_latin_values_readable(page):
    guide = page.locator('.step-guide')
    playwright.expect(guide).to_have_attribute('open', '')
    assert guide.locator('bdi', has_text='23-04-1990').count() == 1
    guide.locator('summary').click()
    step(page, 1)
    playwright.expect(page.locator('.step-guide')).not_to_have_attribute('open', '')


def test_invalid_answers_are_flagged_not_confirmed(page):
    wrap = page.locator('[data-field-wrap="personal.date_of_birth"]')
    field(page, 'personal.date_of_birth').fill('1234')
    page.locator('#step-title').click()
    playwright.expect(wrap.locator('.field-error-message')).to_have_text(
        'Use the format DD-MM-YYYY, for example 23-04-1990.'
    )
    playwright.expect(wrap).not_to_have_class(re.compile('is-ok'))
    playwright.expect(page.locator('#errors-panel')).to_contain_text('Date of birth')
    # Typing hides the old error; a valid answer is then accepted and leaves the error list.
    field(page, 'personal.date_of_birth').fill('31-02-1990')
    playwright.expect(wrap.locator('.field-error-message')).to_have_count(0)
    page.locator('#step-title').click()
    playwright.expect(wrap.locator('.field-error-message')).to_have_text(
        'This date does not exist. Check the day and month.'
    )
    field(page, 'personal.date_of_birth').fill('23-04-1990')
    page.locator('#step-title').click()
    playwright.expect(wrap).to_have_class(re.compile('is-ok'))
    playwright.expect(page.locator('#errors-panel')).to_be_hidden()
    # Spaces only count as an empty answer.
    country = page.locator('[data-field-wrap="personal.country_of_birth"]')
    field(page, 'personal.country_of_birth').fill('   ')
    page.locator('#step-title').click()
    playwright.expect(country).not_to_have_class(re.compile('is-ok'))
    playwright.expect(field(page, 'personal.country_of_birth')).to_have_value('')


def test_json_recovery_and_roundtrip(page):
    page.locator('#json-view').click()
    page.locator('#json-editor').fill('{ invalid JSON')
    page.locator('#apply-json').click()
    playwright.expect(page.locator('#json-status')).to_contain_text('Invalid JSON')
    playwright.expect(page.locator('#save-status')).to_have_text('Saved on this device')
    page.reload()
    page.wait_for_selector('#json-editor')
    playwright.expect(page.locator('#json-editor')).to_have_value('{ invalid JSON')
    page.locator('#form-view').click()
    page.locator('#modal button[value="keep"]').click()
    playwright.expect(field(page, 'personal.given_names')).to_have_value('ALPHA')
    page.locator('#json-view').click()
    data = scenarios()['tourist']
    data['personal']['given_names'] = 'JSON EDIT'
    page.locator('#json-editor').fill(json.dumps(data))
    page.locator('#apply-json').click()
    playwright.expect(page.locator('#json-status')).to_contain_text('JSON applied')
    page.locator('#form-view').click()
    playwright.expect(field(page, 'personal.given_names')).to_have_value('JSON EDIT')
    with page.expect_download() as download:
        page.locator('#export-profile').click()
    saved = json.loads(download.value.path().read_text())
    assert saved['personal']['given_names'] == 'JSON EDIT'
    assert 'confirmed' not in saved and 'marks' not in saved


def test_conditional_clear_is_explicit_and_cancellable(page):
    step(page, 2)
    choose(page, 'residence.lives_outside_country_of_nationality', 'true')
    field(page, 'residence.permit_type').fill('TEST PERMIT')
    page.locator('#step-title').click()
    choose(page, 'residence.lives_outside_country_of_nationality', 'false')
    playwright.expect(page.locator('#modal')).to_be_visible()
    assert 'Residence permit type' in page.locator('#modal-body').inner_text()
    page.locator('#modal-actions button[value="cancel"]').click()
    playwright.expect(chip(page, 'residence.lives_outside_country_of_nationality', 'true')).to_be_checked()
    playwright.expect(field(page, 'residence.permit_type')).to_have_value('TEST PERMIT')
    choose(page, 'residence.lives_outside_country_of_nationality', 'false')
    page.locator('#modal button[value="clear"]').click()
    playwright.expect(page.locator('[data-field="residence.permit_type"]')).to_have_count(0)
    page.locator('#json-view').click()
    assert json.loads(page.locator('#json-editor').input_value())['residence']['permit_type'] is None


def test_incomplete_new_profile_and_error_navigation(page):
    page.locator('#new-profile').click()
    page.locator('#modal-input').fill('New applicant')
    page.locator('#modal button[value="add"]').click()
    step(page, 2)
    playwright.expect(
        page.locator('[data-field="residence.lives_outside_country_of_nationality"]:checked')
    ).to_have_count(0)
    page.locator('#validate').click()
    page.wait_for_selector('.error-link')
    page.locator('.error-link').filter(has_text='Surname:').first.click()
    playwright.expect(page.locator('#step-title')).to_have_text('Personal details')
    playwright.expect(field(page, 'personal.surname')).to_be_focused()
    assert int(page.locator('#progress-percent').inner_text().strip('%')) < 100


def test_generate_four_pages_and_stale_preview(page):
    menu(page, '[data-profile="charlie"]')
    step(page, 7)
    page.locator('#generate').click()
    page.wait_for_selector('#preview-content img', timeout=30000)
    assert page.locator('[data-page]').count() == 4
    for n in range(4):
        page.locator(f'[data-page="{n}"]').click()
        playwright.expect(page.locator('#preview-content img')).to_have_attribute(
            'alt', f'Generated application, page {n + 1}'
        )
    with page.expect_download() as download:
        page.locator('#preview-content a[download]').click()
    assert download.value.suggested_filename == 'charlie_schengen_application_draft.pdf'
    assert download.value.path().read_bytes().startswith(b'%PDF')
    step(page, 0)
    field(page, 'personal.given_names').fill('EDIT AFTER GENERATION')
    page.locator('#step-title').click()
    step(page, 7)
    playwright.expect(page.locator('.preview-stale')).to_be_visible()
    assert page.locator('#preview-content a[download]').count() == 0


def test_import_duplicate_delete_and_clear(page):
    payload = json.dumps(scenarios()['tourist']).encode()
    page.locator('#import-file').set_input_files(
        {'name': 'imported.json', 'mimeType': 'application/json', 'buffer': payload}
    )
    playwright.expect(page.locator('.profile-button')).to_have_count(4)
    menu(page, '#manage-profile')
    page.locator('#modal button[value="duplicate"]').click()
    playwright.expect(page.locator('.profile-button')).to_have_count(5)
    assert page.locator('#current-name').inner_text() == 'imported copy'
    menu(page, '#manage-profile')
    page.locator('#modal button[value="delete"]').click()
    page.locator('#modal button[value="delete"]').click()
    playwright.expect(page.locator('.profile-button')).to_have_count(4)
    menu(page, '#clear-data')
    page.locator('#modal button[value="clear"]').click()
    playwright.expect(page.locator('.profile-button')).to_have_count(0)
    playwright.expect(page.locator('#save-status')).to_have_text('Saved on this device')
    page.reload()
    page.wait_for_selector('.empty-state')
    assert page.locator('.profile-button').count() == 0


def test_all_controls_reachable_in_visual_mode(page):
    seen = set()
    cases = scenarios()
    for name in ['detailed', 'minor', 'choices_06']:
        apply_data(page, cases[name])
        for n in range(8):
            step(page, n)
            seen.update(page.locator('[data-field]').evaluate_all('(els)=>els.map(e=>e.dataset.field)'))
        choose(page, 'application.signature.enabled', 'true')
        seen.update(page.locator('[data-field]').evaluate_all('(els)=>els.map(e=>e.dataset.field)'))
    from webapp.fields import LABELS

    assert seen == set(LABELS)


def test_mobile_layout_and_keyboard(page):
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    step(page, 4)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    field(page, 'journey.arrival_date').focus()
    page.keyboard.press('Tab')
    assert page.evaluate("document.activeElement !== document.body")
    assert page.locator('#next-step').is_visible()


def test_empty_workspace_resets_legacy_data_once(browser, web_server):
    context = new_context(browser)
    page = context.new_page()
    page.goto(web_server.origin)
    page.wait_for_selector('[data-action="new"]')
    # Recreate a legacy database with an old profile and signature.
    page.evaluate("""async () => {
      const {testAdapter} = await import("/app.js");
      testAdapter.closeDB();
      await new Promise((resolve,reject)=>{const r=indexedDB.deleteDatabase('visafilla');r.onsuccess=resolve;r.onerror=reject;});
      await new Promise((resolve,reject)=>{
        const r=indexedDB.open('visafilla',1);
        r.onupgradeneeded=()=>r.result.createObjectStore('workspace');
        r.onerror=reject;
        r.onsuccess=()=>{const tx=r.result.transaction('workspace','readwrite');
          tx.objectStore('workspace').put({version:1,profiles:[{id:'old',signature:'old-image'}],activeId:'old'},'current');
          tx.oncomplete=()=>{r.result.close();resolve();};};
      });
    }""")
    page.reload()
    page.wait_for_selector('[data-action="new"]')
    assert page.locator('.profile-button').count() == 0
    assert page.evaluate('async () => (await import("/app.js")).testAdapter.state.profiles') == []
    assert page.evaluate('async () => (await (await import("/app.js")).testAdapter.readState()).profiles') == []
    page.locator('[data-action="new"]').click()
    page.locator('#modal-input').fill('My applicant')
    page.locator('#modal button[value="add"]').click()
    playwright.expect(field(page, 'personal.given_names')).to_have_value('')
    field(page, 'personal.given_names').fill('MY NEW DATA')
    page.locator('#step-title').click()
    playwright.expect(page.locator('#save-status')).to_have_text('Saved on this device')
    page.reload()
    playwright.expect(field(page, 'personal.given_names')).to_have_value('MY NEW DATA')
    # Clearing from JSON view must show the usable empty workspace.
    page.locator('#json-view').click()
    menu(page, '#clear-data')
    page.locator('#modal button[value="clear"]').click()
    playwright.expect(page.locator('[data-action="new"]')).to_be_visible()
    context.close()


@pytest.mark.parametrize('submit', ['enter', 'click'])
def test_create_blank_applicant_and_export_json(browser, web_server, submit):
    context = new_context(browser, viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.goto(web_server.origin)
    page.locator('[data-action="new"]').click()
    page.locator('#modal-input').fill('   ')
    page.locator('#modal button[value="add"]').click()
    playwright.expect(page.locator('#modal')).to_be_visible()
    page.locator('#modal-input').fill('New applicant')
    if submit == 'enter':
        page.locator('#modal-input').press('Enter')
    else:
        page.locator('#modal button[value="add"]').click()
    playwright.expect(page.locator('.profile-button')).to_have_count(1)
    field(page, 'personal.given_names').fill('MY ANSWER')
    page.locator('#step-title').click()
    playwright.expect(page.locator('#save-status')).to_have_text('Saved on this device')
    with page.expect_download() as download:
        page.locator('#export-profile').click()
    assert json.loads(download.value.path().read_text())['personal']['given_names'] == 'MY ANSWER'
    page.reload()
    playwright.expect(field(page, 'personal.given_names')).to_have_value('MY ANSWER')
    context.close()


def test_blank_biometrics_and_multiple_stays_survive_edits(page):
    data = example()
    data['previous_biometrics'].update(
        fingerprints_taken=None,
        visa_sticker_number='EXAMPLE123',
        visa_issuing_country='AUSTRIA',
        visa_entry_date='15-03-2023',
    )
    data['accommodation']['booking_details'] = 'Madrid 01-06 to 15-06-2027: BOOKING001'
    data['accommodation']['name'] = 'Madrid: Example stay\nBarcelona: Example stay\nParis: Example stay'
    apply_data(page, data)
    step(page, 5)
    playwright.expect(page.locator('[data-field="previous_biometrics.fingerprints_taken"]:checked')).to_have_count(0)
    playwright.expect(field(page, 'previous_biometrics.visa_sticker_number')).to_have_value('EXAMPLE123')
    playwright.expect(field(page, 'previous_biometrics.visa_entry_date')).to_have_value('15-03-2023')
    step(page, 6)
    playwright.expect(field(page, 'accommodation.name')).to_have_value(data['accommodation']['name'])
    playwright.expect(field(page, 'accommodation.booking_details')).to_have_value(
        data['accommodation']['booking_details']
    )
    field(page, 'accommodation.phone').fill('+34 000 000 001')
    page.locator('#step-title').click()
    assert (
        page.evaluate(
            "async () => (await import('/app.js')).testAdapter.current().data.previous_biometrics.visa_sticker_number"
        )
        == 'EXAMPLE123'
    )
    step(page, 7)
    page.locator('#generate').click()
    playwright.expect(page.locator('.preview-tabs button')).to_have_count(4, timeout=30000)


def test_add_edit_remove_accommodation_array(page):
    data = example()
    data['accommodation'] = [dict(data['accommodation'], city='Madrid')]
    apply_data(page, data)
    step(page, 6)
    page.locator('[data-stay-add]').click()
    field(page, 'accommodation.1.city').fill('Barcelona')
    field(page, 'accommodation.1.name').fill('SECOND EXAMPLE STAY')
    field(page, 'accommodation.1.address').fill('123 EXAMPLE STREET, BARCELONA, SPAIN')
    field(page, 'accommodation.1.phone').fill('+34 000 000 002')
    page.locator('#step-title').click()
    assert page.evaluate("async () => (await import('/app.js')).testAdapter.current().data.accommodation.length") == 2
    assert (
        page.evaluate("async () => (await import('/app.js')).testAdapter.current().data.accommodation[1].city")
        == 'Barcelona'
    )
    playwright.expect(field(page, 'accommodation.name')).to_have_value(data['accommodation'][0]['name'])
    step(page, 7)
    page.locator('#generate').click()
    playwright.expect(page.locator('.preview-tabs button')).to_have_count(4, timeout=30000)
    step(page, 6)
    page.locator('[data-stay-remove="0"]').click()
    playwright.expect(field(page, 'accommodation.name')).to_have_value('SECOND EXAMPLE STAY')
    assert page.evaluate("async () => (await import('/app.js')).testAdapter.current().data.accommodation.length") == 1
    page.locator('#json-view').click()
    exported = json.loads(page.locator('#json-editor').input_value())
    assert isinstance(exported['accommodation'], list)
    assert exported['accommodation'][0]['city'] == 'Barcelona'


def test_render_is_read_only_and_typing_does_not_serialize_editor(page):
    result = page.evaluate("""async () => {
      const a = (await import('/app.js')).testAdapter;
      const before = structuredClone(a.state);
      a.render();
      return JSON.stringify(before) === JSON.stringify(a.state);
    }""")
    assert result
    previous = page.evaluate("async () => (await import('/app.js')).testAdapter.current().jsonText")
    field(page, 'personal.given_names').fill('CHANGED NAME')
    assert page.evaluate("async () => (await import('/app.js')).testAdapter.current().jsonText") == previous
    page.locator('#json-view').click()
    assert json.loads(page.locator('#json-editor').input_value())['personal']['given_names'] == 'CHANGED NAME'


def test_unapplied_editor_text_survives_form_edit_save_and_reload(page):
    raw = '{   "unapplied": true  }'
    page.locator('#json-view').click()
    page.locator('#json-editor').fill(raw)
    page.locator('#form-view').click()
    page.locator('#modal button[value="keep"]').click()
    field(page, 'personal.given_names').fill('NEW FORM ANSWER')
    page.evaluate("async () => (await import('/app.js')).testAdapter.persist()")
    page.reload()
    page.wait_for_selector('[data-field="personal.given_names"]')
    playwright.expect(field(page, 'personal.given_names')).to_have_value('NEW FORM ANSWER')
    page.locator('#json-view').click()
    playwright.expect(page.locator('#json-editor')).to_have_value(raw)


def test_first_visit_country_picker_is_remembered_and_changeable(browser, web_server):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.goto(web_server.origin)
    dialog = page.locator('#country-dialog')
    playwright.expect(dialog).to_be_visible()
    # A country must be chosen on the first visit: Escape and close are unavailable.
    page.keyboard.press('Escape')
    playwright.expect(dialog).to_be_visible()
    playwright.expect(page.locator('#country-close')).to_be_hidden()
    assert page.locator('.country-card').count() == 29
    playwright.expect(page.locator('[data-country="FR"]')).to_be_disabled()
    playwright.expect(page.locator('[data-country="FR"]')).to_contain_text('Coming soon')
    page.locator('[data-country="ES"]').click()
    playwright.expect(dialog).to_be_hidden()
    # The how-it-works guide follows the first country choice.
    playwright.expect(page.locator('#welcome-dialog')).to_be_visible()
    page.locator('#welcome-start').click()
    chip = page.locator('#country-switch')
    playwright.expect(chip).to_contain_text('Spain')
    page.reload()
    playwright.expect(page.locator('#country-switch')).to_contain_text('Spain')
    playwright.expect(dialog).to_be_hidden()
    # The chip reopens the picker, which can now be closed without changing anything.
    page.locator('#country-switch').click()
    playwright.expect(dialog).to_be_visible()
    playwright.expect(page.locator('[data-country="ES"]')).to_have_attribute('aria-pressed', 'true')
    page.locator('#country-close').click()
    playwright.expect(dialog).to_be_hidden()
    assert page.evaluate("localStorage.getItem('visafilla.country')") == 'ES'
    context.close()


def test_sidebar_never_scrolls_and_menu_switches_applicants(page):
    for width, height in [(1440, 900), (1280, 700), (1100, 560)]:
        page.set_viewport_size({'width': width, 'height': height})
        overflow = page.evaluate(
            """() => [document.querySelector('.sidebar'), document.querySelector('#steps')]
                .map(el => el.scrollHeight - el.clientHeight)"""
        )
        assert overflow == [0, 0], (width, height, overflow)
        assert page.locator('.side-footer').bounding_box()['y'] + 20 <= height
    assert page.locator('#steps .step-icon svg').count() == 8
    switcher = page.locator('#applicant-switch')
    switcher.click()
    playwright.expect(page.locator('#applicant-menu')).to_be_visible()
    assert switcher.get_attribute('aria-expanded') == 'true'
    page.keyboard.press('Escape')
    playwright.expect(page.locator('#applicant-menu')).to_be_hidden()
    menu(page, '[data-profile="bravo"]')
    playwright.expect(page.locator('#current-name')).to_have_text('Bravo')
    playwright.expect(page.locator('#applicant-menu')).to_be_hidden()
    page.locator('#about').click()
    playwright.expect(page.locator('#modal')).to_contain_text('Not an official service')


def test_sample_applicant_is_removed_when_the_first_real_one_is_added(browser, web_server):
    context = new_context(browser, viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.goto(web_server.origin)
    page.locator('#form-content [data-action="sample"]').click()
    playwright.expect(page.locator('.sample-banner')).to_be_visible()
    playwright.expect(page.locator('#progress-percent')).to_have_text('100%')
    playwright.expect(page.locator('.field-note')).to_have_count(0)
    playwright.expect(page.locator('.profile-button .sample-badge')).to_have_count(1)
    # Only one sample at a time; its menu entry hides while it exists.
    page.locator('#applicant-switch').click()
    playwright.expect(page.locator('#sample-profile')).to_be_hidden()
    page.keyboard.press('Escape')
    page.locator('.sample-banner [data-action="new"]').click()
    page.locator('#modal-input').fill('Me')
    page.locator('#modal button[value="add"]').click()
    playwright.expect(page.locator('.profile-button')).to_have_count(1)
    playwright.expect(page.locator('#current-name')).to_have_text('Me')
    playwright.expect(page.locator('.sample-badge')).to_have_count(0)
    # It can be added again later and is removed again by an import.
    menu(page, '#sample-profile')
    playwright.expect(page.locator('.profile-button')).to_have_count(2)
    page.locator('#import-file').set_input_files(
        files=[{'name': 'mine.json', 'mimeType': 'application/json', 'buffer': json.dumps(example()).encode()}]
    )
    playwright.expect(page.locator('#current-name')).to_have_text('mine')
    playwright.expect(page.locator('.profile-button')).to_have_count(2)
    playwright.expect(page.locator('.sample-badge')).to_have_count(0)
    context.close()


def test_welcome_guide_shows_once_and_reopens_from_help(browser, web_server):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    context.add_init_script("localStorage.setItem('visafilla.country', 'ES')")
    page = context.new_page()
    page.goto(web_server.origin)
    welcome = page.locator('#welcome-dialog')
    playwright.expect(welcome).to_be_visible()
    playwright.expect(page.locator('#welcome-hide')).to_be_checked()
    page.locator('#welcome-start').click()
    page.reload()
    page.wait_for_selector('[data-action="new"]')
    playwright.expect(welcome).to_be_hidden()
    # Help reopens it; unticking the box brings it back on the next visit.
    page.locator('#help').click()
    playwright.expect(welcome).to_be_visible()
    page.locator('#welcome-hide').uncheck()
    page.locator('#welcome-start').click()
    page.reload()
    playwright.expect(welcome).to_be_visible()
    page.locator('#welcome-sample').click()
    playwright.expect(page.locator('.sample-banner')).to_be_visible()
    context.close()
