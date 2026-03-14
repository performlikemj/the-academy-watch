import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Loader2, Plus, FileText, Users, LogOut, TrendingUp, UserPlus, Trash2, MapPin, Building2 } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { APIService } from '@/lib/api'
import { useAuthUI } from '@/context/AuthContext'
import { ManualPlayerModal } from '@/components/ManualPlayerModal'

export function WriterDashboard() {
    const navigate = useNavigate()
    const { logout } = useAuthUI()
    const [loading, setLoading] = useState(true)
    const [teams, setTeams] = useState({ parent_club_assignments: [], loan_team_assignments: [], assignments: [] })
    const [commentaries, setCommentaries] = useState([])
    const [stats, setStats] = useState(null)
    const [error, setError] = useState('')
    const [deletingId, setDeletingId] = useState(null)
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
    const [showManualPlayerModal, setShowManualPlayerModal] = useState(false)

    const loadData = async () => {
        try {
            const [teamsData, commentariesData, statsData] = await Promise.all([
                APIService.getWriterTeams(),
                APIService.getWriterCommentaries(),
                APIService.getJournalistOwnStats().catch(() => null)
            ])
            // Handle both new format (object with arrays) and legacy format (array)
            if (Array.isArray(teamsData)) {
                setTeams({ parent_club_assignments: teamsData, loan_team_assignments: [], assignments: teamsData })
            } else {
                setTeams(teamsData || { parent_club_assignments: [], loan_team_assignments: [], assignments: [] })
            }
            setCommentaries(commentariesData || [])
            setStats(statsData)
        } catch (err) {
            console.error('Failed to load writer data', err)
            setError('Failed to load dashboard data. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        loadData()
    }, [])

    const handleLogout = () => {
        logout()
        navigate('/writer/login')
    }

    const handleDelete = async () => {
        if (!deletingId) return
        try {
            await APIService.deleteWriterCommentary(deletingId)
            setCommentaries(prev => prev.filter(c => c.id !== deletingId))
        } catch (err) {
            console.error('Failed to delete commentary', err)
            setError('Failed to delete commentary')
        } finally {
            setDeletingId(null)
            setShowDeleteConfirm(false)
        }
    }

    const confirmDelete = (id) => {
        setDeletingId(id)
        setShowDeleteConfirm(true)
    }

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-background">
            <header className="bg-card shadow">
                <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8 flex justify-between items-center">
                    <h1 className="text-3xl font-bold text-foreground">Writer Dashboard</h1>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" onClick={() => navigate('/writer/contributors')}>
                            <Users className="mr-2 h-4 w-4" /> Contributors
                        </Button>
                        <Button variant="outline" onClick={handleLogout}>
                            <LogOut className="mr-2 h-4 w-4" /> Logout
                        </Button>
                    </div>
                </div>
            </header>
            <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
                <div className="px-4 py-6 sm:px-0 space-y-6">

                    {error && (
                        <div className="p-4 bg-rose-50 text-rose-700 rounded-md border border-rose-200">
                            {error}
                        </div>
                    )}

                    {/* Subscriber Statistics */}
                    {stats && (
                        <>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <Card className="bg-gradient-to-br from-primary/5 to-card border-primary/10">
                                    <CardHeader className="pb-3">
                                        <CardDescription className="flex items-center text-primary">
                                            <Users className="h-4 w-4 mr-1" />
                                            Total Subscribers
                                        </CardDescription>
                                        <CardTitle className="text-3xl font-bold text-foreground">
                                            {stats.total_subscribers || 0}
                                        </CardTitle>
                                    </CardHeader>
                                </Card>

                                <Card className="bg-gradient-to-br from-emerald-50 to-card border-emerald-100">
                                    <CardHeader className="pb-3">
                                        <CardDescription className="flex items-center text-emerald-600">
                                            <TrendingUp className="h-4 w-4 mr-1" />
                                            Last 7 Days
                                        </CardDescription>
                                        <CardTitle className="text-3xl font-bold text-emerald-900">
                                            +{stats.subscribers_last_7_days || 0}
                                        </CardTitle>
                                    </CardHeader>
                                </Card>

                                <Card className="bg-gradient-to-br from-purple-50 to-card border-purple-100">
                                    <CardHeader className="pb-3">
                                        <CardDescription className="flex items-center text-purple-600">
                                            <UserPlus className="h-4 w-4 mr-1" />
                                            Last 30 Days
                                        </CardDescription>
                                        <CardTitle className="text-3xl font-bold text-purple-900">
                                            +{stats.subscribers_last_30_days || 0}
                                        </CardTitle>
                                    </CardHeader>
                                </Card>
                            </div>

                            {/* Subscriber Growth Chart */}
                            {stats.timeline && stats.timeline.length > 0 && (
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Subscriber Growth</CardTitle>
                                        <CardDescription>Weekly subscriber activity over the last 90 days</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <ResponsiveContainer width="100%" height={300}>
                                            <LineChart data={stats.timeline}>
                                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                                <XAxis
                                                    dataKey="week"
                                                    className="text-xs"
                                                    tickFormatter={(value) => {
                                                        const date = new Date(value)
                                                        return `${date.getMonth() + 1}/${date.getDate()}`
                                                    }}
                                                />
                                                <YAxis className="text-xs" />
                                                <Tooltip
                                                    labelFormatter={(value) => `Week of ${value}`}
                                                    contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #e5e7eb', borderRadius: '8px' }}
                                                />
                                                <Line
                                                    type="monotone"
                                                    dataKey="new_subscribers"
                                                    stroke="#3b82f6"
                                                    strokeWidth={2}
                                                    name="New Subscribers"
                                                    dot={{ fill: '#3b82f6', r: 4 }}
                                                />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </CardContent>
                                </Card>
                            )}

                            {/* Team Breakdown */}
                            {stats.team_breakdown && stats.team_breakdown.length > 0 && (
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Subscribers by Team</CardTitle>
                                        <CardDescription>Your subscriber count for each team you cover</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead>Team</TableHead>
                                                    <TableHead className="text-right">Subscribers</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {stats.team_breakdown.map(team => (
                                                    <TableRow key={team.team_id}>
                                                        <TableCell className="font-medium flex items-center gap-2">
                                                            {team.team_logo && (
                                                                <img src={team.team_logo} alt={team.team_name} className="h-6 w-6 object-contain" />
                                                            )}
                                                            {team.team_name}
                                                        </TableCell>
                                                        <TableCell className="text-right text-lg font-semibold text-primary">
                                                            {team.subscriber_count}
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </CardContent>
                                </Card>
                            )}
                        </>
                    )}

                    {/* Assigned Teams & Coverage */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center">
                                    <Users className="mr-2 h-5 w-5" /> Your Coverage
                                </CardTitle>
                                <CardDescription>Teams and players you are authorized to write about</CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button variant="outline" onClick={() => setShowManualPlayerModal(true)}>
                                    <UserPlus className="h-4 w-4 mr-2" />
                                    Suggest Player
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {/* Parent Club Assignments */}
                            {teams.parent_club_assignments?.length > 0 && (
                                <div>
                                    <h4 className="text-sm font-medium text-foreground/80 mb-2 flex items-center">
                                        <Building2 className="h-4 w-4 mr-1 text-primary" />
                                        Parent Clubs (all academy players)
                                    </h4>
                                    <div className="flex flex-wrap gap-2">
                                        {teams.parent_club_assignments.map(assignment => (
                                            <Badge key={assignment.team_id} variant="secondary" className="text-sm py-1 px-3 bg-primary/5 text-primary border-primary/20">
                                                {assignment.team_name}
                                            </Badge>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Loan Team Assignments */}
                            {teams.loan_team_assignments?.length > 0 && (
                                <div>
                                    <h4 className="text-sm font-medium text-foreground/80 mb-2 flex items-center">
                                        <MapPin className="h-4 w-4 mr-1 text-emerald-600" />
                                        Current Clubs (players currently there)
                                    </h4>
                                    <div className="flex flex-wrap gap-2">
                                        {teams.loan_team_assignments.map(assignment => (
                                            <Badge
                                                key={assignment.loan_team_name}
                                                variant="secondary"
                                                className={`text-sm py-1 px-3 ${assignment.is_custom_team
                                                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                                                    : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                                    }`}
                                            >
                                                {assignment.loan_team_name}
                                                {assignment.is_custom_team && <span className="ml-1 text-xs">(custom)</span>}
                                            </Badge>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Empty State */}
                            {!teams.parent_club_assignments?.length && !teams.loan_team_assignments?.length && (
                                <p className="text-muted-foreground">No teams assigned yet.</p>
                            )}
                        </CardContent>
                    </Card>

                    {/* Writeups */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center">
                                    <FileText className="mr-2 h-5 w-5" /> Your Writeups
                                </CardTitle>
                                <CardDescription>Manage your commentaries and reports</CardDescription>
                            </div>
                            <Button onClick={() => navigate('/writer/writeup-editor')}>
                                <Plus className="mr-2 h-4 w-4" /> New Writeup
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {commentaries.length > 0 ? (
                                <div className="space-y-4">
                                    {commentaries.map(item => (
                                        <div key={item.id} className="flex items-center justify-between p-4 border rounded-lg bg-card hover:bg-secondary transition-colors">
                                            <div>
                                                <h3 className="font-medium text-foreground">{item.title || 'Untitled Writeup'}</h3>
                                                <div className="text-sm text-muted-foreground flex gap-2 mt-1">
                                                    <Badge variant="outline" className="text-xs">{item.commentary_type}</Badge>
                                                    {item.team_name && <span className="text-muted-foreground/70">• {item.team_name}</span>}
                                                    <span className="text-muted-foreground/70">• {new Date(item.created_at).toLocaleDateString()}</span>
                                                    {item.is_premium && <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-200 border-amber-200">Premium</Badge>}
                                                </div>
                                            </div>
                                            <div className="flex gap-2">
                                                <Button variant="ghost" size="sm" asChild>
                                                    <Link to={`/writer/writeup-editor?id=${item.id}`}>Edit</Link>
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => confirmDelete(item.id)}
                                                    className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-8 text-muted-foreground">
                                    <p>No writeups found. Start by creating one!</p>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </main>

            {/* Delete Confirmation Dialog */}
            <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Writeup</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this writeup? This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel onClick={() => setDeletingId(null)}>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDelete}
                            className="bg-rose-600 hover:bg-rose-700"
                        >
                            Delete
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <ManualPlayerModal
                open={showManualPlayerModal}
                onOpenChange={setShowManualPlayerModal}
            />
        </div>
    )
}
