import time
import json
import os
import concurrent.futures
import re
import subprocess
import tempfile
import shutil
from .helpers import code_completion, clean_file_name
from django.conf import settings

# Constants and directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_animations")
CODE_DIR = os.path.join(BASE_DIR, "generated_code")
MEDIA_DIR = os.path.join(BASE_DIR, "media_output")
MAX_RETRY_ATTEMPTS = 2

# Create necessary directories
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CODE_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)


def prepare_prompts(animation_guide):
    """
    Prepares prompts from the animation guide and creates a mapping of scene IDs.
    Returns a tuple of (prompts, scene_mapping).
    """
    prompts = []
    scene_mapping = {}
    count = 0

    for topic_idx, topic in enumerate(animation_guide["topic_guides"]):
        topic_title = topic["title"].replace(" ", "_").lower()

        for scene_idx, scene in enumerate(topic["scenes"]):
            user_prompt = scene["script"]
            prompts.append((count, user_prompt))

            # Store mapping information
            scene_mapping[count] = {
                "topic_idx": topic_idx,
                "topic_title": topic_title,
                "scene_idx": scene_idx,
            }
            count += 1

    return prompts, scene_mapping


def extract_code_from_response(response):
    """Extract Python code blocks from the LLM response."""
    code_blocks = re.findall(r"```python\s*(.*?)\s*```", response, re.DOTALL)
    return code_blocks


def write_code_to_file(code_block, file_path):
    """Write code to a file."""

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code_block)


def extract_class_name(code_block):
    """Extract the class name from a code block."""
    class_names = re.findall(r"class\s+(\w+)\s*\(.*\):", code_block)
    if not class_names:
        return None
    return class_names[0]  # Use the first class defined in the file


def run_manim_command(py_file_path, class_name, scene_media_dir, timeout=300):
    """Run manim command and return (success, error_message)."""
    os.makedirs(scene_media_dir, exist_ok=True)

    cmd = ["manim", "-ql", "--media_dir", scene_media_dir, py_file_path, class_name]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout  # 5 minute timeout
        )

        if result.returncode == 0:
            return True, None
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, f"Execution timed out after {timeout} seconds"
    except Exception as e:
        return False, str(e)


def find_video_output_path(scene_media_dir, py_file_path, class_name):
    """Find the output video file path based on manim conventions."""
    last_filename = os.path.basename(py_file_path).split(".")[0]
    quality = "480p15"
    video_file = os.path.join(
        scene_media_dir, "videos", last_filename, quality, f"{class_name}.mp4"
    )

    if os.path.exists(video_file):
        return video_file
    return None


def execute_code_block(code_block, topic_title, scene_idx, output_dir):
    """Execute a code block using manim command and return (video_path, error_message)."""
    # Create a filename based on the topic and scene
    base_name = f"scene_{scene_idx + 1}"
    py_file_path = os.path.join(output_dir, f"{base_name}.py")

    # Write the code to a file
    write_code_to_file(code_block, py_file_path)

    # Extract class name
    class_name = extract_class_name(code_block)
    if not class_name:
        return None, "Could not find class name in the generated code."

    # Create a unique media output directory for this scene
    scene_folder_name = clean_file_name(f"{topic_title}_scene_{scene_idx + 1}")
    scene_media_dir = os.path.join(MEDIA_DIR, scene_folder_name)

    # Run manim
    print(f"Rendering animation for {topic_title}, scene {scene_idx + 1}")
    start = time.time()
    success, error_message = run_manim_command(
        py_file_path, class_name, scene_media_dir
    )
    end = time.time()
    print(f"Time taken for manim: {end - start:.2f} seconds")

    if success:
        print(
            f"Successfully rendered animation for {topic_title}, scene {scene_idx + 1}"
        )
        video_file = find_video_output_path(scene_media_dir, py_file_path, class_name)

        if video_file:
            return video_file, None
        else:
            error_msg = f"Video file not found at expected path"
            print(f"Warning: {error_msg}")
            return None, error_msg
    else:
        print(f"Error rendering animation for {topic_title}, scene {scene_idx + 1}:")
        # print only last 10 lines of error message
        print("\n".join(error_message.split("\n")[-10:]))
        return None, error_message


def generate_fix_prompt(original_scene, error_message):
    """Generate a prompt to fix code based on error message."""
    return f"""
    I need you to fix the following Manim animation code that's producing an error.
    
    Original script: {original_scene['script']}
    
    The code generated an error: {error_message}
    
    Please provide a corrected version of the Manim code that will render successfully.
    Make sure to handle any edge cases and follow Manim best practices.
    """


def save_scene_data(output_data, filepath):
    """Save scene data to a JSON file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def attempt_code_generation_and_execution(
    user_prompt,
    topic_title,
    scene_idx,
    topic_code_dir,
    video_system,
    original_scene=None,
    retry_count=0,
    previous_error=None,
):
    """Generate code using LLM and attempt to execute it, returning result data."""
    # Get response from LLM
    response = code_completion(system=video_system, user=user_prompt, max_tokens=5000)

    # Extract code blocks
    code_blocks = extract_code_from_response(response)

    if not code_blocks:
        print(
            f"No code blocks found in response for {topic_title}, scene {scene_idx + 1}"
        )
        return None, None, response, None

    # Execute the first code block
    video_path, error_message = execute_code_block(
        code_blocks[0], topic_title, scene_idx, topic_code_dir
    )

    # Save the code to a file for reference (with retry suffix if applicable)
    if retry_count > 0:
        code_file_path = os.path.join(
            topic_code_dir, f"scene_{scene_idx + 1}_retry_{retry_count}.py"
        )
    else:
        code_file_path = os.path.join(topic_code_dir, f"scene_{scene_idx + 1}.py")

    write_code_to_file(code_blocks[0], code_file_path)

    return video_path, error_message, response, code_blocks[0]


def process_prompt(prompt_data, scene_mapping, animation_guide, video_system):
    """Process a single prompt and execute the resulting code."""
    prompt_id, user_prompt = prompt_data
    mapping = scene_mapping[prompt_id]
    topic_title = mapping["topic_title"]
    scene_idx = mapping["scene_idx"]
    topic_idx = mapping["topic_idx"]

    # Get original scene data
    original_scene = animation_guide["topic_guides"][topic_idx]["scenes"][scene_idx]

    # Create topic directories
    topic_dir = os.path.join(OUTPUT_DIR, clean_file_name(topic_title))
    topic_code_dir = os.path.join(CODE_DIR, clean_file_name(topic_title))
    os.makedirs(topic_dir, exist_ok=True)
    os.makedirs(topic_code_dir, exist_ok=True)

    # Create filename for this scene
    filename = f"scene_{scene_idx + 1}.json"
    filepath = os.path.join(topic_dir, filename)

    # Attempt initial code generation and execution
    video_path, error_message, response, code = attempt_code_generation_and_execution(
        user_prompt,
        topic_title,
        scene_idx,
        topic_code_dir,
        video_system,
        original_scene,
    )

    # Prepare output data
    output_data = {
        "scene_idx": scene_idx,
        "script": original_scene["script"],
        "generated_response": response,
    }

    # Retry logic if initial attempt failed
    retry_count = 0
    while video_path is None and retry_count < MAX_RETRY_ATTEMPTS:
        retry_count += 1
        print(
            f"Retry {retry_count}: Generating new code for {topic_title}, scene {scene_idx + 1}"
        )

        # Create a fix prompt based on the error
        retry_prompt = generate_fix_prompt(original_scene, error_message)

        # Attempt code generation and execution with the fix prompt
        video_path, error_message, new_response, new_code = (
            attempt_code_generation_and_execution(
                retry_prompt,
                topic_title,
                scene_idx,
                topic_code_dir,
                video_system,
                original_scene,
                retry_count,
                error_message,
            )
        )

        # Update output data with retry information
        output_data[f"retry_{retry_count}_response"] = new_response
        output_data["retry_count"] = retry_count

    # Update the output data with final results
    output_data["video_path"] = video_path
    if error_message:
        output_data["error_message"] = error_message

    # Save to JSON file
    save_scene_data(output_data, filepath)

    return {
        "custom_id": f"{prompt_id}",
        "topic_title": topic_title,
        "scene_idx": scene_idx,
        "response": response,
        "video_path": video_path,
        "error_message": error_message,
    }


def create_summary(results, animation_guide):
    """Create a summary of generated files and videos."""
    summary = {"topics": [], "scenes": []}

    # Organize results by topic and create a flat list of scenes
    topic_videos = {}
    all_scenes = []

    for result in results:
        topic_title = result["topic_title"]
        scene_idx = result["scene_idx"]

        # Create a scene entry
        scene_entry = {
            "topic_title": topic_title,
            "scene_idx": scene_idx,
            "video_path": result["video_path"],
            "folder_name": (
                f"{topic_title}_scene_{scene_idx + 1}" if result["video_path"] else None
            ),
        }
        all_scenes.append(scene_entry)

        # Track videos by topic
        if topic_title not in topic_videos:
            topic_videos[topic_title] = []

        if result["video_path"]:
            topic_videos[topic_title].append(
                {"scene_idx": scene_idx, "video_path": result["video_path"]}
            )

    # Build the summary structure for topics
    for topic_idx, topic in enumerate(animation_guide["topic_guides"]):
        topic_title = topic["title"].replace(" ", "_").lower()
        topic_entry = {
            "title": topic["title"],
            "directory": topic_title,
            "scenes": [],
            "videos": [],
        }

        for scene_idx in range(len(topic["scenes"])):
            scene_file = f"scene_{scene_idx + 1}.json"
            topic_entry["scenes"].append(
                {
                    "scene_idx": scene_idx,
                    "filename": scene_file,
                    "path": os.path.join(topic_title, scene_file),
                }
            )

        # Add video paths for this topic
        if topic_title in topic_videos:
            # Sort videos by scene index
            sorted_videos = sorted(
                topic_videos[topic_title], key=lambda x: x["scene_idx"]
            )
            topic_entry["videos"] = [
                v["video_path"] for v in sorted_videos if v["video_path"]
            ]

        summary["topics"].append(topic_entry)

    # Add the scenes to the summary
    summary["scenes"] = sorted(
        all_scenes, key=lambda x: (x["topic_title"], x["scene_idx"])
    )

    return summary


def merge_videos_with_ffmpeg(video_paths, output_filename="merged_course.mp4"):
    """
    Merge multiple video files using ffmpeg and save to Django media folder.

    Args:
        video_paths: List of video file paths to merge
        output_filename: Name of the output merged video file

    Returns:
        str: Path to the merged video file, or None if merge failed
    """
    if not video_paths:
        print("No video paths provided for merging")
        return None

    # Filter out None values and ensure all files exist
    valid_videos = [path for path in video_paths if path and os.path.exists(path)]

    if not valid_videos:
        print("No valid video files found for merging")
        return None

    if len(valid_videos) == 1:
        print("Only one video file found, copying to media directory")
        # Copy the single video to media directory for static serving
        static_media_dir = settings.MEDIA_ROOT
        os.makedirs(static_media_dir, exist_ok=True)
        
        output_path = os.path.join(static_media_dir, output_filename)
        
        try:
            # Copy the file to media directory
            shutil.copy2(valid_videos[0], output_path)
            print(f"Successfully copied single video to: {output_path}")
            return output_path
        except Exception as e:
            print(f"Error copying single video to media directory: {str(e)}")
            return None

    static_media_dir = settings.MEDIA_ROOT

    # Ensure media directory exists
    os.makedirs(static_media_dir, exist_ok=True)

    # Create output path in Django media folder
    output_path = os.path.join(static_media_dir, output_filename)

    # Create a temporary file list for ffmpeg concat
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        concat_file = f.name
        for video_path in valid_videos:
            # Escape single quotes and write file path
            escaped_path = video_path.replace("'", "'\"'\"'")
            f.write(f"file '{escaped_path}'\n")

    try:
        # Run ffmpeg concat command
        cmd = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-c",
            "copy",
            "-y",  # Overwrite output file if it exists
            output_path,
        ]

        print(f"Merging {len(valid_videos)} videos into {output_filename}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0:
            print(f"Successfully merged videos into: {output_path}")
            return output_path
        else:
            print(f"Error merging videos: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        print("Video merge timed out after 10 minutes")
        return None
    except Exception as e:
        print(f"Error running ffmpeg: {str(e)}")
        return None
    finally:
        # Clean up temporary file
        try:
            os.unlink(concat_file)
        except:
            pass


def generate_animation_videos(animation_guide):
    """
    Generate animation videos from animation guide JSON.
    Returns a summary of generated files and videos.
    """
    # go one step up from utils to the root directory
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    video_system = open(
        os.path.join(BASE_DIR, "prompts/code.txt"), "r", encoding="utf-8"
    ).read()

    # Prepare prompts and scene mapping
    prompts, scene_mapping = prepare_prompts(animation_guide)

    print(f"Processing {len(prompts)} animation scenes...")
    start = time.time()

    # Use ThreadPoolExecutor to process prompts in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Pass scene_mapping, animation_guide, and video_system to each process_prompt call
        results = list(
            executor.map(
                lambda p: process_prompt(
                    p, scene_mapping, animation_guide, video_system
                ),
                prompts,
            )
        )

    end = time.time()
    print(
        f"Time taken for processing: {(end - start) // 60} minutes {(end - start) % 60:.2f} seconds"
    )

    video_paths = [result["video_path"] for result in results if result["video_path"]]
    return merge_videos_with_ffmpeg(video_paths, "merged_course.mp4")


def main():
    # Load animation guide for backward compatibility
    animation_guide = json.load(open("animation_guide.json", "r"))
    generate_animation_videos(animation_guide)


if __name__ == "__main__":
    main()
