# Work with media

Start Open Imagine and select Image, Video, or Voice. The available controls follow the selected model.

## Choose a theme

Open the aperture menu at the top right and choose a theme. The choice is remembered in this browser.
Darkroom, Leica M, Kodak Instamatic, and Polaroid SX-70 remain available alongside four studio themes:

| Theme | Appearance |
|---|---|
| Blueprint | Cobalt drafting grids, cyan accents, and technical typography. |
| Cel Studio | Animation paper, pencil-blue rules, and vermilion details. |
| Broadcast | Graphite consoles, ivory controls, and segmented progress meters. |
| Risograph | Cream paper, teal and coral ink, and offset print borders. |

Every theme applies to Image, Video, and Voice. Theme surfaces sit behind the previews;
the media itself keeps its original colors. Controls and actions stay in the same places.

## Browse the gallery

Choose **Browse** above any gallery to expand its strip into a grid while keeping one main preview.
Search prompts, scripts, voice descriptions, model names, or seeds. Filter by model or mode
and choose newest or oldest first. **Group batches** appears when existing operation identities
identify multiple results; open a batch to browse its items and use **All results** to return.

Choose **Select** to mark several results, or select all results matching the current filters.
Download selected saves the complete files; Remove selected asks for confirmation and uses the
same deletion behavior as each gallery's Remove action. Changing filters clears the bulk selection.
The main Voice player's Download action still downloads its chosen time selection.

Visible Video thumbnails silently loop sixteen small frames from the first two seconds (or the whole clip if shorter).
Previews reuse the local video copies and a bounded cache of small image strips, with one
decoder used at a time during capture. They stop when hidden, during Video generation,
or when reduced motion is enabled. Full-quality playback stays in the main player.

Arrow keys browse results. In the grid, Up/Down move a row and Home/End reach the first/last item.
Space plays or pauses the current Video or Voice preview. Escape leaves multiple selection,
then collapses the browser. Typing and ordinary player controls keep their own keyboard behavior.

Each tab remembers its selected item, gallery layout, filters, and scroll position across refreshes
when **Keep in this browser** is enabled. View preferences are separate for each tab and workspace.

## Reuse and edit a result

Select one gallery item, then use its Edit action to prepare the input. Viewing a result alone does not select it for editing.
Use the action menu to reuse its prompt, script, voice, or seed where offered.
Removing an input reference clears that input; deleting gallery media is a separate action.

In Video Edit, choose **Custom** in the effect picker to describe your own change without a LoRA.
Custom uses the input clip as conditioning and requires no effect weights or downloads.
This is experimental: preservation of the source and adherence to the change are not yet validated.
The named effects instead load their specialized LoRAs and use their measured recipes.

For multiple Image edits, add the images as references and choose one result per image.
Add per-reference instructions when each image needs a different change.
Leaving the references as one composition produces one combined image instead.

## Send a reference to another workspace

Use an Image result as a Video keyframe through its action menu.
In Video, capture a source clip’s timeline frame for Image or as a new keyframe.
The imported source clip and generated results have separate galleries.

In Voice, choose a completed clip and drag the waveform’s edge handles or enter Start and End times.
Click the waveform to seek; use Play to hear the selection. Playback speed changes preview speed only.
Use the action menu to send the selection to Video or Clone. These actions prepare inputs without starting a run.
Download or Edit acts on the selection where supported.

## Use prompt aids

Choose Templates for a starting prompt or script. Add a Look where the selected model supports it.
Use Image Rewrite to expand a prompt with the dedicated Image enhancer.
Video Rewrite expands the editable prompt; Generate also applies native enhancement automatically.
For AuK Design, pick a voice Template or write a custom description separately from the spoken script.
For Drama-3, put delivery directions in the script and provide a matching transcript when cloning.

## Keep drafts and results

Turn on **Keep in this browser** to retain drafts, references, and saved gallery items across reloads.
A completed operation clears its submitted inputs; newer input drafts are preserved.
Download media to keep it outside browser storage. Audio selection downloads include the selected time range in the filename.
Turn Keep off to clear saved browser media and drafts.

## Cancel a run

Use the shared operation control to cancel. Open tabs follow the same operation, including work started by the API.
Voice shows an illustrative waveform while preparing, fills it according to reported progress,
and holds it while saving. The actual audio waveform appears once the result is ready.
Elapsed time and percentages stay in the shared operation bar; reduced motion disables the animation.
Completed batch items remain available; cancelled inputs are retained for another attempt.
