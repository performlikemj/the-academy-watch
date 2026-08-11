import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import { formatDateOnly, toLocalISODate } from '@/lib/dateOnly'

export function UniversalDatePicker({ onDateChange, className = "" }) {
    const [startDate, setStartDate] = useState('')
    const [endDate, setEndDate] = useState('')
    const [isCustomRange, setIsCustomRange] = useState(false)

    const handlePresetChange = useCallback((preset) => {
        const today = new Date()
        let start, end

        switch (preset) {
            case 'today':
                start = end = toLocalISODate(today)
                break
            case 'this_week':
                {
                    const monday = new Date(today)
                    monday.setDate(today.getDate() - today.getDay() + 1)
                    const sunday = new Date(monday)
                    sunday.setDate(monday.getDate() + 6)
                    start = toLocalISODate(monday)
                    end = toLocalISODate(sunday)
                }
                break
            case 'this_month':
                start = toLocalISODate(new Date(today.getFullYear(), today.getMonth(), 1))
                end = toLocalISODate(new Date(today.getFullYear(), today.getMonth() + 1, 0))
                break
            case 'last_30_days':
                {
                    const thirtyDaysAgo = new Date(today)
                    thirtyDaysAgo.setDate(today.getDate() - 30)
                    start = toLocalISODate(thirtyDaysAgo)
                    end = toLocalISODate(today)
                }
                break
            case 'last_90_days':
                {
                    const ninetyDaysAgo = new Date(today)
                    ninetyDaysAgo.setDate(today.getDate() - 90)
                    start = toLocalISODate(ninetyDaysAgo)
                    end = toLocalISODate(today)
                }
                break
            case 'last_year':
                start = toLocalISODate(new Date(today.getFullYear() - 1, today.getMonth(), today.getDate()))
                end = toLocalISODate(today)
                break
            case 'all_time':
                start = '2020-01-01' // Reasonable start date for football data
                end = toLocalISODate(today)
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
                    Showing data from <strong>{formatDateOnly(startDate, {})}</strong> to <strong>{formatDateOnly(endDate, {})}</strong>
                </div>
            )}
        </div>
    )
}
