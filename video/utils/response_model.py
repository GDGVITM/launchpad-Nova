from pydantic import BaseModel
from typing import List

# Content structure models
class Topic(BaseModel):
    """
    Represents a main topic with its related subtopics.
    
    Attributes:
        title: The main topic title
        subtopics: List of subtopic titles under this main topic
    """
    title: str
    subtopics: List[str]

class CourseOutline(BaseModel):
    """
    Represents the complete course structure with multiple topics.
    
    Attributes:
        topics: List of Topic objects forming the course structure
    """
    topics: List[Topic]

# Script content models
class ContentSegment(BaseModel):
    """
    Represents a single segment of educational content.
    
    Attributes:
        text: The actual content text for this segment
    """
    text: str

class TopicScript(BaseModel):
    """
    Contains the complete script for a specific topic.
    
    Attributes:
        segments: List of content segments that form this topic's script
        title: The title of the topic this script covers
    """
    segments: List[ContentSegment]
    title: str

class CourseScript(BaseModel):
    """
    Contains all scripts for the entire course.
    
    Attributes:
        topic_scripts: List of TopicScript objects for all topics in the course
    """
    topic_scripts: List[TopicScript]

# Animation and visual guidance models
class AnimationScene(BaseModel):
    """
    Represents a single scene with its animation instructions and corresponding script.
    
    Attributes:
        script: The script text that accompanies this animation
    """
    script: str

class TopicAnimationGuide(BaseModel):
    """
    Contains all animation scenes for a specific topic.
    
    Attributes:
        title: The title of the topic these animations cover
        scenes: List of AnimationScene objects for this topic
    """
    title: str
    scenes: List[AnimationScene]

class CourseAnimationGuide(BaseModel):
    """
    Contains all animation guides for the entire course.
    
    Attributes:
        topic_guides: List of TopicAnimationGuide objects for all topics
    """
    topic_guides: List[TopicAnimationGuide]

