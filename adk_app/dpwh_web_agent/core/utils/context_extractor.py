"""
Extract conversational context from user questions and parsed actions.

This module identifies entities (cities, regions, contractors, years) from questions
and stores them as context for follow-up questions.
"""
from __future__ import annotations
import re
from typing import Dict, Any, Optional
import pandas as pd


def extract_context_from_question(question: str, parsed_action: Dict[str, Any], df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Extract context entities from a question and its parsed action.
    
    Args:
        question: The user's question
        parsed_action: The parsed action dictionary from simple_parse
        df: Optional dataframe for validation
    
    Returns:
        Dictionary of context entities like:
        {
            'municipality': 'Quezon City',
            'region': '3',
            'contractor': 'XYZ Construction',
            'year': 2023,
            'last_action': 'count',
            'last_column': 'approved_budget_num'
        }
    """
    context = {}
    
    # Extract from parsed filters
    filters = parsed_action.get('filters', {})
    if filters:
        for key in ['municipality', 'province', 'region', 'contractor', 'project_location', 'main_island']:
            if key in filters and filters[key]:
                context[key] = filters[key]
    
    # Extract from time filters
    time_filters = parsed_action.get('time', {})
    if time_filters:
        if 'year' in time_filters:
            context['year'] = time_filters['year']
        if 'year_range' in time_filters:
            context['year_range'] = time_filters['year_range']
        if 'years' in time_filters:
            context['years'] = time_filters['years']
    
    # Store last action type for context
    if 'action' in parsed_action and parsed_action['action'] not in ['unknown', 'more_projects']:
        context['last_action'] = parsed_action['action']
    
    # Store column if specified
    if 'column' in parsed_action and parsed_action['column']:
        context['last_column'] = parsed_action['column']
    
    # Extract top_n if specified
    if 'top_n' in parsed_action:
        context['last_top_n'] = parsed_action['top_n']
    
    return context


def apply_context_to_question(question: str, context: Dict[str, Any]) -> str:
    """
    Enhance a question with stored context if the question is ambiguous.
    
    Args:
        question: The user's current question
        context: Stored context from previous questions
    
    Returns:
        Enhanced question with context applied
    
    Example:
        Context: {'municipality': 'Quezon City'}
        Question: "What's the total budget?"
        Returns: "What's the total budget in Quezon City?"
    """
    q_lower = question.lower().strip()
    
    # Don't apply context for project ID lookups
    # Project IDs typically look like: P00549881VS, ABC-123-DEF, etc.
    if re.search(r'\b[A-Z0-9]{6,20}\b', question, re.IGNORECASE):
        return question
    
    # Don't apply context if question is about a specific project
    if any(pattern in q_lower for pattern in ['project id', 'projectid']):
        return question
    
    # Handle pronoun references to contractors: "that contractor", "this contractor"
    if any(pattern in q_lower for pattern in ['that contractor', 'this contractor', 'the contractor', 'that company', 'this company']):
        if 'contractor' in context:
            # Replace the pronoun with the actual contractor name
            enhanced_question = question
            for pattern in ['that contractor', 'this contractor', 'the contractor', 'that company', 'this company']:
                if pattern in q_lower:
                    enhanced_question = re.sub(
                        pattern, 
                        f"contractor {context['contractor']}", 
                        enhanced_question, 
                        flags=re.IGNORECASE
                    )
            return enhanced_question
    
    # Handle implicit project references: "who is the contractor" after mentioning a project
    if q_lower.strip() in ['who is the contractor', 'what is the contractor', 'contractor']:
        if 'last_project_id' in context:
            return f"who is the contractor of {context['last_project_id']}"
    
    # Handle "show me" as implicit request to list projects in stored context
    if q_lower.strip() in ['show me', 'list them', 'list', 'show them', 'show']:
        if any(k in context for k in ['municipality', 'province', 'region', 'last_project_id']):
            # Convert to explicit request for top projects
            if 'municipality' in context:
                return f"show me top 5 projects in {context['municipality']}"
            elif 'province' in context:
                return f"show me top 5 projects in {context['province']}"
            elif 'region' in context:
                return f"show me top 5 projects in region {context['region']}"
            elif 'last_project_id' in context:
                return f"show me details of {context['last_project_id']}"
    
    # Handle other implicit project detail questions
    if 'last_project_id' in context:
        if q_lower.strip() in ['what is the budget', 'budget', 'how much', 'what is the cost']:
            return f"what is the budget of {context['last_project_id']}"
        if q_lower.strip() in ['where is it', 'location', 'where']:
            return f"where is {context['last_project_id']}"
    
    # Don't apply context if the question already has location/contractor info
    has_explicit_filter = any(word in q_lower for word in [
        ' in ', ' from ', ' by ', ' at ', ' for ',
        'region', 'city', 'municipality', 'province'
    ])
    
    # IMPORTANT: If question mentions a different location, don't mix contexts
    if has_explicit_filter:
        return question
    
    # Apply context to ambiguous questions
    enhanced_parts = [question.rstrip('?')]
    
    # Add location context
    if 'municipality' in context:
        enhanced_parts.append(f"in {context['municipality']}")
    elif 'province' in context:
        enhanced_parts.append(f"in {context['province']}")
    elif 'region' in context:
        region_val = context['region']
        # Format region properly
        if str(region_val).isdigit():
            enhanced_parts.append(f"in region {region_val}")
        else:
            enhanced_parts.append(f"in {region_val}")
    elif 'project_location' in context:
        enhanced_parts.append(f"in {context['project_location']}")
    
    # Add contractor context if relevant
    if 'contractor' in context and any(word in q_lower for word in ['contractor', 'company', 'who']):
        enhanced_parts.append(f"for contractor {context['contractor']}")
    
    # Add year context if relevant
    if 'year' in context and any(word in q_lower for word in ['year', 'when', 'date']):
        enhanced_parts.append(f"in {context['year']}")
    
    if len(enhanced_parts) > 1:
        return ' '.join(enhanced_parts)
    
    return question


def should_clear_context(question: str) -> bool:
    """
    Determine if the question indicates a topic change that should clear context.
    
    Returns True if question suggests starting a new topic.
    """
    q_lower = question.lower().strip()
    
    # Don't clear context for project ID lookups - they're standalone queries
    if re.search(r'\b[A-Z0-9]{6,20}\b', question, re.IGNORECASE):
        return False
    
    # Don't clear for specific project detail questions
    if any(pattern in q_lower for pattern in ['project id', 'who is the contractor of', 'what is the budget of']):
        return False
    
    # Don't clear for simple follow-up questions that should use context
    simple_followups = [
        'what is the highest budget',
        'what is the total budget',
        'what is the average',
        'show top',
        'who is the contractor',
        'how much',
        'what is the cost',
    ]
    if any(followup in q_lower for followup in simple_followups):
        return False
    
    # Clear context when new location is EXPLICITLY mentioned with "in" keyword
    # Pattern: "projects in X", "in region X", "in city Y"
    if re.search(r'\b(?:in|from)\s+(?:region|province|city|municipality|cebu|manila|quezon)', q_lower):
        return True
    
    # Clear context on explicit new topic indicators
    clear_indicators = [
        'show me', 'list', 'find', 'search',
        'how many projects', 'count projects',
        'tell me about', 'what about',
    ]
    
    # Check if it's a new query (not a follow-up)
    if any(q_lower.startswith(indicator) for indicator in clear_indicators):
        return True
    
    # Check for explicit location changes
    location_change_patterns = [
        r'\bin\s+(?:a\s+different|another|other)\s+',
        r'switch\s+to',
        r'change\s+to',
        r'instead\s+of',
    ]
    
    for pattern in location_change_patterns:
        if re.search(pattern, q_lower):
            return True
    
    return False


def get_contextual_summary(context: Dict[str, Any]) -> str:
    """
    Generate a human-readable summary of current context.
    
    Returns:
        A string describing the current context, e.g., "Quezon City, Region NCR, 2023"
    """
    parts = []
    
    if 'municipality' in context:
        parts.append(context['municipality'])
    elif 'province' in context:
        parts.append(context['province'])
    
    if 'region' in context:
        region = context['region']
        if str(region).upper() in ['NCR', 'NATIONAL CAPITAL REGION']:
            parts.append('NCR')
        elif str(region).upper() in ['CAR', 'CORDILLERA']:
            parts.append('CAR')
        else:
            parts.append(f"Region {region}")
    
    if 'contractor' in context:
        parts.append(f"Contractor: {context['contractor']}")
    
    if 'year' in context:
        parts.append(str(context['year']))
    elif 'year_range' in context:
        yr = context['year_range']
        parts.append(f"{yr[0]}-{yr[1]}")
    
    return ', '.join(parts) if parts else 'No active context'
