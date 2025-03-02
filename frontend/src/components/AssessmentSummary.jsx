import React, { memo } from 'react';
import PropTypes from 'prop-types';
import '../styles/AssessmentSummary.css';

const AssessmentSummary = memo(({ assessment }) => {
    if (!assessment) return null;
    
    return (
        <div 
            className="assessment-summary" 
            role="region" 
            aria-label="Assessment summary"
        >
            <h4>Assessment Summary</h4>
            <div className="assessment-condition">
                <strong>Condition:</strong> {assessment.condition}
                {assessment.confidence && (
                    <span> - {assessment.confidence}% confidence</span>
                )}
            </div>
            {assessment.recommendation && (
                <div className="assessment-recommendation">
                    <strong>Recommendation:</strong> {assessment.recommendation}
                </div>
            )}
        </div>
    );
});

AssessmentSummary.displayName = 'AssessmentSummary';
AssessmentSummary.propTypes = {
    assessment: PropTypes.shape({
        condition: PropTypes.string,
        confidence: PropTypes.number,
        recommendation: PropTypes.string
    })
};

export default AssessmentSummary;