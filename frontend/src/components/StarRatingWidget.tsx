import React, { useState, useEffect, useRef } from 'react';
import { StarIcon } from '@heroicons/react/24/solid';
import { StarIcon as StarIconOutline } from '@heroicons/react/24/outline';
import axios from 'axios';

interface RatingDetail {
  user: string;
  rating: number;
}

interface RatingInfoResponse {
  num_stars: number;
  rating_details: RatingDetail[];
}

interface StarRatingWidgetProps {
  resourceType: 'agents' | 'servers';
  path: string;
  initialRating?: number;
  initialCount?: number;
  authToken?: string | null;
  onShowToast?: (message: string, type: 'success' | 'error') => void;
  onRatingUpdate?: (newRating: number) => void;
}


const StarRatingWidget: React.FC<StarRatingWidgetProps> = ({
  resourceType,
  path,
  initialRating = 0,
  initialCount = 0,
  authToken,
  onShowToast,
  onRatingUpdate
}) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [selectedRating, setSelectedRating] = useState<number | null>(null);
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [currentUserRating, setCurrentUserRating] = useState<number | null>(null);
  const [averageRating, setAverageRating] = useState(initialRating);
  const [ratingCount, setRatingCount] = useState(initialCount);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);


  // Load current rating on mount
  useEffect(() => {
    if (authToken) {
      loadCurrentRating();
    }
  }, [resourceType, path, authToken]);


  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };

    if (isDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isDropdownOpen]);


  const loadCurrentRating = async () => {
    try {
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : undefined;
      // Both servers and agents now use consistent path parameter pattern
      const url = `/api/${resourceType}${path}/rating`;
      const response = await axios.get<RatingInfoResponse>(
        url,
        headers ? { headers } : undefined
      );

      setAverageRating(response.data.num_stars);
      setRatingCount(response.data.rating_details.length);

      // Find current user's rating
      // Extract username from JWT token (simplified - in production use proper JWT parsing)
      if (authToken && response.data.rating_details) {
        // For now, check if any rating exists - in production, match by username
        const userRating = response.data.rating_details[0]; // Simplified
        if (userRating) {
          setCurrentUserRating(userRating.rating);
          setSelectedRating(userRating.rating);
        }
      }
    } catch (error: any) {
      console.error('Failed to load rating:', error);
    }
  };


  const handleSubmitRating = async () => {
    console.log('handleSubmitRating called', { selectedRating, authToken: !!authToken });
    if (!selectedRating || !authToken) {
      console.log('Validation failed - no rating or token');
      return;
    }

    setIsSubmitting(true);
    try {
      const headers = { Authorization: `Bearer ${authToken}` };
      // Both servers and agents now use consistent path parameter pattern
      const url = `/api/${resourceType}${path}/rate`;
      console.log('Submitting rating to:', url, { rating: selectedRating });

      const response = await axios.post(
        url,
        { rating: selectedRating },
        { headers }
      );

      console.log('Rating response:', response.data);
      const newAverageRating = response.data.average_rating;
      setAverageRating(newAverageRating);
      setCurrentUserRating(selectedRating);

      // Update count (increment if new rating, keep same if update)
      if (!currentUserRating) {
        setRatingCount(prev => prev + 1);
      }

      setShowSuccess(true);

      if (onShowToast) {
        onShowToast(
          currentUserRating ? 'Rating updated successfully!' : 'Rating submitted successfully!',
          'success'
        );
      }

      if (onRatingUpdate) {
        onRatingUpdate(newAverageRating);
      }

      // Auto-close after 2 seconds
      console.log('Setting timeout to close dialog...');
      setTimeout(() => {
        console.log('Closing dialog now');
        setShowSuccess(false);
        setIsDropdownOpen(false);
      }, 2000);
    } catch (error: any) {
      console.error('Failed to submit rating:', error);
      console.error('Error details:', error.response?.data);
      if (onShowToast) {
        onShowToast(
          error.response?.data?.detail || 'Failed to submit rating',
          'error'
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };


  const handleStarClick = (rating: number) => {
    setSelectedRating(rating);
  };


  const handleCancel = () => {
    setIsDropdownOpen(false);
    setSelectedRating(currentUserRating);
    setHoverRating(null);
  };


  const renderStars = (count: number, filled: boolean, size: 'small' | 'large' = 'large') => {
    const sizeClass = size === 'small' ? 'h-4 w-4' : 'h-6 w-6';
    const IconComponent = filled ? StarIcon : StarIconOutline;

    return (
      <IconComponent
        className={`${sizeClass} ${filled ? 'text-yellow-400' : 'text-gray-300 dark:text-gray-600'}`}
      />
    );
  };


  const displayRating = hoverRating !== null ? hoverRating : (selectedRating || currentUserRating || 0);


  return (
    <div className="relative" ref={dropdownRef}>
      {/* Rating Display - Clickable */}
      <button
        onClick={() => setIsDropdownOpen(!isDropdownOpen)}
        className="flex items-center gap-2 hover:bg-yellow-50 dark:hover:bg-yellow-900/20 p-2 rounded-lg transition-colors duration-200"
        title={`Click to rate this ${resourceType.slice(0, -1)}`}
        aria-label={`Rate this ${resourceType.slice(0, -1)}`}
        aria-expanded={isDropdownOpen}
        aria-haspopup="dialog"
      >
        <div className="p-1.5 bg-yellow-50 dark:bg-yellow-900/30 rounded">
          <StarIcon className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
        </div>
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {averageRating > 0 ? averageRating.toFixed(1) : '0'}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {ratingCount === 0 ? 'No ratings' : `${ratingCount} rating${ratingCount !== 1 ? 's' : ''}`}
          </div>
        </div>
      </button>

      {/* Rating Dropdown */}
      {isDropdownOpen && (
        <div
          className="absolute top-full left-0 mt-2 w-80 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 z-50 p-4"
          role="dialog"
          aria-label={`${resourceType.slice(0, -1)} rating form`}
        >
          {/* Success State */}
          {showSuccess ? (
            <div className="text-center py-6">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-full mb-3">
                <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
                Rating {currentUserRating && selectedRating !== currentUserRating ? 'updated' : 'submitted'}!
              </h4>
              <div className="flex justify-center items-center gap-1 mb-2">
                {[1, 2, 3, 4, 5].map((star) => (
                  <div key={star}>
                    {renderStars(star, star <= (selectedRating || 0), 'small')}
                  </div>
                ))}
                <span className="ml-2 text-sm text-gray-600 dark:text-gray-400">
                  ({selectedRating} stars)
                </span>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                New average: {averageRating.toFixed(1)} ★
              </p>
            </div>
          ) : isSubmitting ? (
            // Loading State
            <div className="text-center py-6">
              <div className="inline-flex items-center justify-center w-12 h-12 mb-3">
                <svg className="animate-spin h-8 w-8 text-cyan-600" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                Submitting your rating...
              </p>
            </div>
          ) : (
            // Rating Form
            <>
              <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
                {currentUserRating ? 'Update your rating:' : `Rate this ${resourceType.slice(0, -1)}:`}
              </h4>
              {currentUserRating && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  Currently: {currentUserRating} stars
                </p>
              )}

              {/* Star Selection */}
              <div
                className="flex items-center justify-center gap-2 my-4"
                role="radiogroup"
                aria-label="Select rating"
              >
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    onClick={() => handleStarClick(star)}
                    onMouseEnter={() => setHoverRating(star)}
                    onMouseLeave={() => setHoverRating(null)}
                    className="p-1 hover:scale-110 transition-transform duration-150 focus:outline-none focus:ring-2 focus:ring-yellow-400 rounded"
                    role="radio"
                    aria-checked={selectedRating === star}
                    aria-label={`${star} star${star !== 1 ? 's' : ''}`}
                  >
                    {renderStars(star, star <= displayRating)}
                  </button>
                ))}
              </div>

              {/* Rating Preview Text */}
              {displayRating > 0 && (
                <p className="text-center text-sm text-gray-600 dark:text-gray-400 mb-4">
                  {displayRating} star{displayRating !== 1 ? 's' : ''}
                </p>
              )}

              {/* Action Buttons */}
              <div className="flex gap-2 mt-4">
                <button
                  onClick={handleCancel}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmitRating}
                  disabled={!selectedRating}
                  className="flex-1 px-4 py-2 text-sm font-medium text-white bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg transition-colors duration-200 flex items-center justify-center gap-2"
                >
                  {currentUserRating ? 'Update Rating' : 'Submit Rating'}
                  {selectedRating && (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};


export default StarRatingWidget;
