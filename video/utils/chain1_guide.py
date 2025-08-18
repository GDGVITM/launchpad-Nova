
import os
from .response_model import CourseOutline, TopicScript, CourseScript, TopicAnimationGuide, CourseAnimationGuide
from .helpers import parse_json,  llama_chat_completion, gemini_chat_completion
# Generate animation guide for each script segment in parallel
import concurrent.futures


def get_chat_func():# -> Callable[..., str | None]:
    return gemini_chat_completion


def process_segment(segment, animation_system):
    user_prompt = [{"text": segment.text}]
    kwargs = {
        "max_tokens": 5000,
        "thinking_budget": 5000,
    }
    animation_raw = get_chat_func()(animation_system, str(user_prompt), **kwargs)
    decoded_animation_raw = parse_json(animation_raw, r_finder="[", l_finder="]")
    
    scene_data = ""
    if decoded_animation_raw and len(decoded_animation_raw) > 0:
        for scene in decoded_animation_raw:
            scene_data += f"Script: {segment.text}\nAnimation: {scene['animation']}\n\n"
    
    return {"script": scene_data} if scene_data else None


def generate_animation_json(user_prompt):
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    toc_system = open(os.path.join(BASE_DIR, "prompts/toc.txt"), "r").read()
    script_system = open(os.path.join(BASE_DIR, "prompts/script.txt"), "r").read()
    animation_system = open(os.path.join(BASE_DIR, "prompts/animation.txt"), "r", encoding="utf-8").read()

    # Store all the topic scripts
    topic_scripts = []
    topic_animation_guides = []

    # Generate course outline
    outline_raw = get_chat_func()(toc_system, user_prompt)
    course_outline = CourseOutline(**parse_json(outline_raw))

    # DEMO MODE: Only generate one script segment for fast rendering
    topics_to_include = 1
    subtopics_to_include = 1
    script_to_include = 1
    segments_to_include = 1  # Only process first segment for demo

    # Format topics and subtopics as text for prompt
    topics_subtopics_text = ""
    for topic in course_outline.topics[:topics_to_include]:
        topics_subtopics_text += f"{topic.title}\n"
        for subtopic in topic.subtopics[:subtopics_to_include]:
            topics_subtopics_text += f"  - {subtopic}\n"

    # Generate script for each topic
    for topic in course_outline.topics[:topics_to_include]:
        topic_user_prompt = f"out of the following topics\n{topics_subtopics_text}\n\nI want to learn about {topic.title}\n\nCreate a script for me to learn about it"
        script_raw = get_chat_func()(script_system, topic_user_prompt)
        topic_script = TopicScript(segments=parse_json(script_raw, r_finder="[", l_finder="]"), title=topic.title)
        topic_scripts.append(topic_script)

    course_script = CourseScript(topic_scripts=topic_scripts)

    for script in course_script.topic_scripts[:script_to_include]:
        # DEMO MODE: Only process the first segment for fast rendering
        segments_to_process = script.segments[:segments_to_include]
        
        # Create a list to store scenes in chronological order
        topic_scenes = [None] * len(segments_to_process)
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Map segments to their index position to maintain order later
            future_to_index = {
                executor.submit(process_segment, segment, animation_system): idx 
                for idx, segment in enumerate(segments_to_process)
            }
            
            # As futures complete, place them in the correct position in topic_scenes
            for future in concurrent.futures.as_completed(future_to_index):
                idx = future_to_index[future]
                result = future.result()
                if result:
                    topic_scenes[idx] = result
        
        # Filter out any None values (if any segments failed to process)
        topic_scenes = [scene for scene in topic_scenes if scene is not None]
        
        animation_guide = TopicAnimationGuide(scenes=topic_scenes, title=script.title)
        topic_animation_guides.append(animation_guide)

    # Create the full course animation guide
    course_animation_guide = CourseAnimationGuide(topic_guides=topic_animation_guides)
    
    return course_animation_guide.model_dump()



