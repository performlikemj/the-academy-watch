import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'

export function UniversalDatePicker({ onDateChange, className = "" }) {
    const [startDate, setStartDate] = useState('')
    const [endDate, setEndDate] = useState('')
    const [isCustomRange, setIsCustomRange] = useState(false)

    const handlePresetChange = useCallback((preset) => {
        const today = new Date()
        let start, end

        switch (preset) {
            case 'today':
                start = end = today.toISOString().split('T')[0]
                break
            case 'this_week':
                {
                    const monday = new Date(today)
                    monday.setDate(today.getDate() - today.getDay() + 1)
                    start = monday.toISOString().split('T')[0]
                    end = new Date(monday.getTime() + 6 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
                }
                break
            case 'this_month':
                start = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0]
                end = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().split('T')[0]
                break
            case 'last_30_days':
                start = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
                end = today.toISOString().split('T')[0]
                break
            case 'last_90_days':
                start = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
                end = today.toISOString().split('T')[0]
                break
            case 'last_year':
                start = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate()).toISOString().split('T')[0]
                end = today.toISOString().split('T')[0]
                break
            case 'all_time':
                start = '2020-01-01' // Reasonable start date for football data
                end = today.toISOString().split('T')[0]
                break
            case 'custom':
                setIsCustomRange(true)
                return
            default:
                return
        }

        setStartDate(start)
        setEndDate(end)
        setIsCustomRange(false)
        onDateChange({ startDate: start, endDate: end, preset })
    }, [onDateChange])

    const handleCustomDateChange = () => {
        if (startDate && endDate) {
            onDateChange({ startDate, endDate, preset: 'custom' })
        }
    }

    useEffect(() => {
        // Set default to last 30 days
        handlePresetChange('last_30_days')
    }, [handlePresetChange])

    return (
        <div className={`space-y-4 ${className}`}>
            <div className="flex flex-wrap gap-2">
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('today')}
                >
                    Today
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('this_week')}
                >
                    This Week
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('this_month')}
                >
                    This Month
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('last_30_days')}
                >
                    Last 30 Days
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('last_90_days')}
                >
                    Last 90 Days
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('last_year')}
                >
                    Last Year
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('all_time')}
                >
                    All Time
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePresetChange('custom')}
                >
                    Custom Range
                </Button>
            </div>

            {isCustomRange && (
                <div className="flex items-center space-x-4 p-4 border rounded-lg bg-secondary">
                    <div className="flex items-center space-x-2">
                        <Label htmlFor="start-date">Start Date:</Label>
                        <Input
                            id="start-date"
                            type="date"
                            value={startDate}
                            onChange={(e) => setStartDate(e.target.value)}
                            className="w-40"
                        />
                    </div>
                    <div className="flex items-center space-x-2">
                        <Label htmlFor="end-date">End Date:</Label>
                        <Input
                            id="end-date"
                            type="date"
                            value={endDate}
                            onChange={(e) => setEndDate(e.target.value)}
                            className="w-40"
                        />
                    </div>
                    <Button
                        size="sm"
                        onClick={handleCustomDateChange}
                        disabled={!startDate || !endDate}
                    >
                        Apply
                    </Button>
                </div>
            )}

            {(startDate && endDate) && (
                <div className="text-sm text-muted-foreground bg-primary/5 p-2 rounded">
                    Showing data from <strong>{new Date(startDate).toLocaleDateString()}</strong> to <strong>{new Date(endDate).toLocaleDateString()}</strong>
                </div>
            )}
        </div>
    )
}
