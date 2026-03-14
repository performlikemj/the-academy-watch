import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Loader2, Plus, Clock, CheckCircle, XCircle } from 'lucide-react'
import { APIService } from '@/lib/api'

export function ManualPlayerModal({ open, onOpenChange }) {
    const [activeTab, setActiveTab] = useState('new')
    const [submissions, setSubmissions] = useState([])
    const [loadingSubmissions, setLoadingSubmissions] = useState(false)

    // Form state
    const [formData, setFormData] = useState({
        player_name: '',
        team_name: '',
        league_name: '',
        position: '',
        notes: ''
    })
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState(null)
    const [success, setSuccess] = useState(null)

    useEffect(() => {
        if (open && activeTab === 'history') {
            loadSubmissions()
        }
    }, [open, activeTab])

    const loadSubmissions = async () => {
        setLoadingSubmissions(true)
        try {
            const data = await APIService.listManualSubmissions()
            setSubmissions(Array.isArray(data) ? data : [])
        } catch (err) {
            console.error('Failed to load submissions', err)
        } finally {
            setLoadingSubmissions(false)
        }
    }

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (!formData.player_name.trim() || !formData.team_name.trim()) {
            setError('Player Name and Team Name are required')
            return
        }

        setSubmitting(true)
        setError(null)
        setSuccess(null)

        try {
            await APIService.submitManualPlayer(formData)
            setSuccess('Player submitted successfully! An admin will review your request.')
            setFormData({
                player_name: '',
                team_name: '',
                league_name: '',
                position: '',
                notes: ''
            })
            // Refresh history if we switch tabs later
            if (activeTab === 'history') loadSubmissions()
        } catch (err) {
            console.error('Failed to submit player', err)
            setError(err.message || 'Failed to submit player')
        } finally {
            setSubmitting(false)
        }
    }

    const getStatusBadge = (status) => {
        switch (status) {
            case 'approved':
                return <Badge className="bg-green-600"><CheckCircle className="h-3 w-3 mr-1" /> Approved</Badge>
            case 'rejected':
                return <Badge variant="destructive"><XCircle className="h-3 w-3 mr-1" /> Rejected</Badge>
            default:
                return <Badge variant="secondary"><Clock className="h-3 w-3 mr-1" /> Pending</Badge>
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px] max-h-[85vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle>Suggest Manual Player</DialogTitle>
                    <DialogDescription>
                        Submit a player that isn't automatically tracked by our system.
                    </DialogDescription>
                </DialogHeader>

                <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="new">New Submission</TabsTrigger>
                        <TabsTrigger value="history">My Submissions</TabsTrigger>
                    </TabsList>

                    <TabsContent value="new" className="mt-4 space-y-4 overflow-y-auto pr-1">
                        {error && (
                            <div className="bg-red-50 text-red-600 p-3 rounded-md text-sm">
                                {error}
                            </div>
                        )}
                        {success && (
                            <div className="bg-green-50 text-green-600 p-3 rounded-md text-sm">
                                {success}
                            </div>
                        )}

                        <form id="manual-player-form" onSubmit={handleSubmit} className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label htmlFor="player_name">Player Name *</Label>
                                    <Input
                                        id="player_name"
                                        value={formData.player_name}
                                        onChange={(e) => setFormData({ ...formData, player_name: e.target.value })}
                                        placeholder="e.g. John Doe"
                                        required
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="team_name">Team Name *</Label>
                                    <Input
                                        id="team_name"
                                        value={formData.team_name}
                                        onChange={(e) => setFormData({ ...formData, team_name: e.target.value })}
                                        placeholder="e.g. Falkirk"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label htmlFor="league_name">League (Optional)</Label>
                                    <Input
                                        id="league_name"
                                        value={formData.league_name}
                                        onChange={(e) => setFormData({ ...formData, league_name: e.target.value })}
                                        placeholder="e.g. Scottish Championship"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="position">Position (Optional)</Label>
                                    <Input
                                        id="position"
                                        value={formData.position}
                                        onChange={(e) => setFormData({ ...formData, position: e.target.value })}
                                        placeholder="e.g. Forward"
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="notes">Notes / Source (Optional)</Label>
                                <Textarea
                                    id="notes"
                                    value={formData.notes}
                                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                                    placeholder="Link to transfer news or other details..."
                                    rows={3}
                                />
                            </div>
                        </form>
                    </TabsContent>

                    <TabsContent value="history" className="mt-4 flex-1 overflow-y-auto min-h-0 pr-1">
                        {loadingSubmissions ? (
                            <div className="flex justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin" />
                            </div>
                        ) : submissions.length === 0 ? (
                            <p className="text-center text-muted-foreground py-8">No submissions yet.</p>
                        ) : (
                            <div className="space-y-3">
                                {submissions.map((sub) => (
                                    <div key={sub.id} className="border rounded-lg p-3 text-sm">
                                        <div className="flex justify-between items-start mb-2">
                                            <div>
                                                <span className="font-medium">{sub.player_name}</span>
                                                <span className="text-muted-foreground mx-1">at</span>
                                                <span className="font-medium">{sub.team_name}</span>
                                            </div>
                                            {getStatusBadge(sub.status)}
                                        </div>
                                        <div className="text-muted-foreground text-xs grid grid-cols-2 gap-2">
                                            <div>League: {sub.league_name || '-'}</div>
                                            <div>Pos: {sub.position || '-'}</div>
                                            <div className="col-span-2">Submitted: {new Date(sub.created_at).toLocaleDateString()}</div>
                                            {sub.admin_notes && (
                                                <div className="col-span-2 mt-1 p-2 bg-muted rounded text-xs">
                                                    <strong>Admin Note:</strong> {sub.admin_notes}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </TabsContent>
                </Tabs>

                <DialogFooter className="mt-4">
                    <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
                    {activeTab === 'new' && (
                        <Button type="submit" form="manual-player-form" disabled={submitting}>
                            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                            Submit Player
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
