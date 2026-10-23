# Signpost profile (template)

Everything specific to one person lives in a profile, never in the skill. The skill reads the profile at the start of a run; if the profile is missing, or a value the run needs is blank, the skill asks for the missing values, writes them to the profile (not to this template) and carries on (`SKILL.md`, First run: the profile).

Where it lives: `config/zotero-reading-signpost-profile.md` in the working folder, or the path the project's instructions name. Keep the filled-in profile out of anything published.

Copy the block below into the profile and fill it in. Leave a value blank where it does not apply.

```
signpost_colour: #c9a27a
signpost_tag_by_colour_rule: yes or no
summary_length_cap: 15%
ai_rules_file: <path to the record of AI rules for taught modules; blank if there are none>
graph_notes_template: <path to the Reading Notes template; blank if there is none>
graph_reading_pages: <folder or pages that list each reading, used for `related::`; blank if none>

libraries:
- name: <library name>
  kind: personal or group
  lane: <which of notes, annotations and the OCR copy the lane names, and which collections it covers (name and key)>
- name: <another library>
  kind: group
  lane: <as above>

module_reading_list: <library and collection key the module readings come from; blank if none>
patch_log: <path of the log file where each field change is recorded; blank if the user keeps none>
```

What each value does:
- `signpost_colour`: the one highlight colour for everything this skill creates (hex).
- `signpost_tag_by_colour_rule`: whether the user's own Zotero colour rule adds a Signpost tag when that colour is applied. The skill never adds a tag itself.
- `summary_length_cap`: the share of the summarised pages' word count the summary aims at; a guide, not a limit.
- `ai_rules_file`: the file step 0 reads before any run on a taught-module reading.
- `graph_notes_template`, `graph_reading_pages`: where the Signpost Summary note's layout and `related::` value come from (`references/method.md` section 1).
- `libraries`: the write lane for each library (`references/rules.md`, Write lanes); a library or action not named here is outside the lane.
- `module_reading_list`: where module readings are listed (step 0 and `references/cases.md` sections 1, Module AI-rules gate, and 10, Shared or group library lanes).
- `patch_log`: the file where each field change is logged (`references/cases.md` section 13, Patch log).
