"""Narrated-only extension. Configured by main.py before serving requests.
Legacy dialogue projects remain readable but cannot be resumed or edited.
"""
from __future__ import annotations
import math
import re
from functools import wraps

PRESETS = {
    'stickman': {
        'label': 'Stickman animation',
        'image_type': '2d',
        'style': 'Clean 2D stick-figure illustration: circular heads, simple line limbs, consistent bold line thickness and proportions, minimal uncluttered backgrounds, flat limited colours, readable silhouettes, clear 16:9 composition. Distinguish recurring figures with a fixed accessory or accent colour. Text-free artwork.',
        'motion': ' Readable stick-figure gestures and simple joint movement, stable line thickness and proportions, minimal camera movement, consistent flat illustrated backgrounds.',
        'planning': 'Plan STICKMAN visuals. Use one clear action or visual metaphor per shot. Express emotion through posture and gestures. Keep circular heads, line limbs and simple props; describe recurring figures using a fixed accent colour or accessory instead of realistic facial anatomy. Avoid complex crowds and tiny details. Keep spatial relationships and action direction consistent between scenes.',
    },
    'claymation': {
        'label': 'Faceless claymation',
        'image_type': '3d',
        'style': 'Handcrafted stop-motion claymation miniature set, tactile matte plasticine with subtle fingerprints, rounded faceless clay figures with smooth featureless heads, fixed clay colours and body proportions, handmade clay props, soft studio lighting, gentle depth of field, clear 16:9 composition. Text-free artwork.',
        'motion': ' Deliberate small stop-motion-style increments, tactile handmade clay movement, restrained gestures and camera movement, fixed figure proportions and clay colours, smooth featureless faces throughout.',
        'planning': 'Plan FACELESS CLAYMATION visuals. Every person is a handmade clay figure with a smooth featureless head. Convey emotion through posture, gesture, spacing and lighting rather than eyes, mouths or lip movement. Lock each figure clay colour, shape and proportions. Use miniature clay sets and simple physical actions suitable for stop-motion, with one main action per shot and continuity of props and positions.',
    },
}


def duration(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('Length must be a number between 0.5 and 15 minutes.') from None
    if not math.isfinite(result) or not 0.5 <= result <= 15:
        raise ValueError('Length must be between 0.5 and 15 minutes.')
    return result


def interface_html(html):
    html = re.sub(r'<button\b[^>]*\bdata-t="(?:dialogue|both)"[^>]*>.*?</button>', '', html, flags=re.S)
    html = re.sub(r'(<input\b[^>]*\bid="nMin"[^>]*\bmax=")10(")', r'\g<1>15\2', html)
    html = html.replace('the AI writes the script or screenplay from this', 'the AI writes the narration script from this')
    html = html.replace('longer than the 10-min export limit', 'longer than the configured export limit')
    script = """<script>
(() => {
  const voiceMode = document.getElementById('s_dialogue_voice_mode');
  if (voiceMode) voiceMode.closest('div').hidden = true;
  const originalSetType = setType;
  setType = () => originalSetType('narrated');
  const minutes = document.getElementById('nMin');
  if (minutes) minutes.max = '15';
  const type = document.getElementById('nType');
  if (type) type.value = 'narrated';
  const originalRender = render;
  render = function() {
    originalRender();
    if (P && ['dialogue', 'both'].includes(P.story_type)) {
      const main = document.getElementById('main');
      const note = document.createElement('div');
      note.className = 'banner';
      note.textContent = 'Archived dialogue project: read-only in narrated-only mode. Create a new narrated video to continue.';
      main.prepend(note);
      main.querySelectorAll('button, input, textarea, select').forEach(el => el.disabled = true);
    }
  };
})();
</script>"""
    if '</body>' not in html:
        raise ValueError('Interface is missing its closing body tag.')
    return html.replace('</body>', script + '\n</body>', 1)


def configure(app):
    if app.extensions.get('narrated_only'):
        return
    from flask import jsonify, request
    from . import brain as B, pipeline as PL, planner as P, project as PR, ve as VE
    B.STYLE_PRESETS.update(PRESETS)
    PR.DEFAULT_SETTINGS['export_cap_seconds'] = 900
    PR.DEFAULT_SETTINGS['narrated_upgrade_done'] = False
    settings = PR.load_settings()
    if not settings.get('narrated_upgrade_done'):
        changes = {'narrated_upgrade_done': True}
        if settings.get('export_cap_seconds') == 600:
            changes['export_cap_seconds'] = 900
        PR.save_settings(changes)

    original_normalise = B.normalise_analysis
    @wraps(original_normalise)
    def normalise(analysis, preset):
        result = original_normalise(analysis, preset)
        result['_preset'] = preset
        if preset in PRESETS:
            result['visual_style'] = PRESETS[preset]['style']
        return result
    B.normalise_analysis = PL.normalise_analysis = normalise

    original_analysis = B.Brain.analysis_prompt
    @wraps(original_analysis)
    def analysis_prompt(self, script, preset):
        system, task = original_analysis(self, script, preset)
        if preset in PRESETS:
            system += '\n' + PRESETS[preset]['planning']
        return system, task
    B.Brain.analysis_prompt = analysis_prompt

    original_scenes = B.Brain.scenes_prompt
    @wraps(original_scenes)
    def scenes_prompt(self, analysis, scenes):
        system, task = original_scenes(self, analysis, scenes)
        preset = analysis.get('_preset')
        if preset not in PRESETS and PL.RUN.project:
            preset = PL.RUN.project.state.get('preset')
        if preset in PRESETS:
            system += '\n' + PRESETS[preset]['planning']
        return system, task
    B.Brain.scenes_prompt = scenes_prompt

    original_keyframe = VE.VideoExpress.keyframe
    @wraps(original_keyframe)
    async def keyframe(self, prompt, image_type, timeout_s=240):
        current = PL.RUN.project
        preset = current.state.get('preset') if current else None
        if preset in PRESETS:
            image_type = PRESETS[preset]['image_type']
        return await original_keyframe(self, prompt, image_type, timeout_s)
    VE.VideoExpress.keyframe = keyframe

    original_diagnose = VE.VideoExpress.diagnose
    @wraps(original_diagnose)
    async def diagnose(self, voice, image_type):
        checks = await original_diagnose(self, voice, image_type)
        return [(ok, message) for ok, message in checks if not message.startswith('Dialogue tools:')]
    VE.VideoExpress.diagnose = diagnose

    def new_project():
        d = request.get_json() or {}
        if not isinstance(d, dict):
            raise ValueError('Expected a project object.')
        minutes = duration(d.get('minutes', 5))
        script = str(d.get('script') or '').strip()
        topic = str(d.get('topic') or '').strip()
        if len(script) < 40 and len(topic) < 8:
            raise ValueError('Type a topic for the AI to write about, or paste your own narration script.')
        preset = d.get('preset') or PR.load_settings()['preset']
        if preset not in B.STYLE_PRESETS:
            raise ValueError('Choose an available visual preset.')
        name = str(d.get('name') or '').strip() or (topic or script.split('\n')[0])[:60]
        p = PR.Project.create(name, script, preset)
        p.state.update(story_type='narrated', topic=topic, reference=str(d.get('reference') or '').strip(),
                       notes=str(d.get('notes') or '').strip(), minutes=minutes)
        p.state['estimate_s'] = (round(P.estimate_seconds(P.clean_script(script), PR.load_settings()['wpm']))
                                 if script else round(minutes * 60))
        p.save()
        if d.get('start'):
            PL.RUN.start('all', p, lambda: PL.step_all(p))
        return jsonify(p.summary())
    app.view_functions['new_project'] = new_project

    @app.before_request
    def narrated_policy():
        if request.method != 'POST':
            return None
        slug = (request.view_args or {}).get('slug')
        if slug and PR.open_project(slug).state.get('story_type', 'narrated') != 'narrated':
            return jsonify(error='Legacy dialogue projects are read-only. Create a new narrated project.'), 409
        if request.endpoint == 'edit_characters':
            return jsonify(error='Character dialogue voices are disabled. Edit visual descriptions in the visual bible.'), 409
        return None

    @app.after_request
    def narrated_interface(response):
        if request.endpoint == 'index' and response.status_code == 200:
            response.direct_passthrough = False
            response.set_data(interface_html(response.get_data(as_text=True)))
            response.headers.pop('ETag', None)
            response.headers.pop('Last-Modified', None)
            response.headers['Cache-Control'] = 'no-store'
        return response

    app.extensions['narrated_only'] = True
