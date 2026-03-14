import React, { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
    Loader2,
    Plus,
    Trash2,
    Edit,
    GripVertical,
    ExternalLink,
    Eye,
    EyeOff,
    MousePointerClick,
    Image as ImageIcon,
} from 'lucide-react'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog'
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
import { APIService } from '@/lib/api'

export function AdminSponsors() {
    const [sponsors, setSponsors] = useState([])
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)

    // Dialog states
    const [editDialogOpen, setEditDialogOpen] = useState(false)
    const [editingSponsor, setEditingSponsor] = useState(null)
    const [deleteConfirmSponsor, setDeleteConfirmSponsor] = useState(null)

    // Form state
    const [formData, setFormData] = useState({
        name: '',
        image_url: '',
        link_url: '',
        description: '',
        is_active: true,
    })
    const [formErrors, setFormErrors] = useState({})

    // Drag state for reordering
    const [draggedId, setDraggedId] = useState(null)

    useEffect(() => {
        loadSponsors()
    }, [])

    const loadSponsors = async () => {
        try {
            setLoading(true)
            const data = await APIService.adminGetSponsors()
            setSponsors(data.sponsors || [])
        } catch (error) {
            console.error('Failed to load sponsors:', error)
        } finally {
            setLoading(false)
        }
    }

    const validateForm = () => {
        const errors = {}
        if (!formData.name.trim()) errors.name = 'Name is required'
        if (!formData.image_url.trim()) errors.image_url = 'Image URL is required'
        if (!formData.link_url.trim()) errors.link_url = 'Link URL is required'
        
        // Basic URL validation
        try {
            if (formData.image_url.trim()) new URL(formData.image_url.trim())
        } catch {
            errors.image_url = 'Invalid image URL'
        }
        try {
            if (formData.link_url.trim()) new URL(formData.link_url.trim())
        } catch {
            errors.link_url = 'Invalid link URL'
        }

        setFormErrors(errors)
        return Object.keys(errors).length === 0
    }

    const handleOpenCreate = () => {
        setEditingSponsor(null)
        setFormData({
            name: '',
            image_url: '',
            link_url: '',
            description: '',
            is_active: true,
        })
        setFormErrors({})
        setEditDialogOpen(true)
    }

    const handleOpenEdit = (sponsor) => {
        setEditingSponsor(sponsor)
        setFormData({
            name: sponsor.name || '',
            image_url: sponsor.image_url || '',
            link_url: sponsor.link_url || '',
            description: sponsor.description || '',
            is_active: sponsor.is_active ?? true,
        })
        setFormErrors({})
        setEditDialogOpen(true)
    }

    const handleSave = async () => {
        if (!validateForm()) return

        try {
            setSaving(true)
            if (editingSponsor) {
                await APIService.adminUpdateSponsor(editingSponsor.id, formData)
            } else {
                await APIService.adminCreateSponsor(formData)
            }
            setEditDialogOpen(false)
            loadSponsors()
        } catch (error) {
            console.error('Failed to save sponsor:', error)
            alert(error.message || 'Failed to save sponsor')
        } finally {
            setSaving(false)
        }
    }

    const handleDelete = async () => {
        if (!deleteConfirmSponsor) return

        try {
            setSaving(true)
            await APIService.adminDeleteSponsor(deleteConfirmSponsor.id)
            setDeleteConfirmSponsor(null)
            loadSponsors()
        } catch (error) {
            console.error('Failed to delete sponsor:', error)
            alert(error.message || 'Failed to delete sponsor')
        } finally {
            setSaving(false)
        }
    }

    const handleToggleActive = async (sponsor) => {
        try {
            await APIService.adminUpdateSponsor(sponsor.id, {
                is_active: !sponsor.is_active
            })
            loadSponsors()
        } catch (error) {
            console.error('Failed to toggle sponsor:', error)
        }
    }

    // Drag and drop reordering
    const handleDragStart = (e, sponsorId) => {
        setDraggedId(sponsorId)
        e.dataTransfer.effectAllowed = 'move'
    }

    const handleDragOver = (e, targetId) => {
        e.preventDefault()
        if (draggedId === targetId) return

        const newSponsors = [...sponsors]
        const draggedIndex = newSponsors.findIndex(s => s.id === draggedId)
        const targetIndex = newSponsors.findIndex(s => s.id === targetId)

        if (draggedIndex !== -1 && targetIndex !== -1) {
            const [draggedItem] = newSponsors.splice(draggedIndex, 1)
            newSponsors.splice(targetIndex, 0, draggedItem)
            setSponsors(newSponsors)
        }
    }

    const handleDragEnd = async () => {
        if (!draggedId) return

        try {
            const sponsorIds = sponsors.map(s => s.id)
            await APIService.adminReorderSponsors(sponsorIds)
        } catch (error) {
            console.error('Failed to save order:', error)
            loadSponsors() // Revert on error
        }
        setDraggedId(null)
    }

    if (loading) {
        return (
            <div className="flex justify-center items-center min-h-[400px]">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between lg:items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Sponsors</h2>
                    <p className="text-muted-foreground">
                        Manage sponsor ads displayed in the sidebar
                    </p>
                </div>
                <Button className="w-full sm:w-auto" onClick={handleOpenCreate}>
                    <Plus className="mr-2 h-4 w-4" /> Add Sponsor
                </Button>
            </div>

            {/* Stats */}
            <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Sponsors</CardDescription>
                        <CardTitle className="text-2xl">{sponsors.length}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Active</CardDescription>
                        <CardTitle className="text-2xl text-emerald-600">
                            {sponsors.filter(s => s.is_active).length}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Inactive</CardDescription>
                        <CardTitle className="text-2xl text-muted-foreground/70">
                            {sponsors.filter(s => !s.is_active).length}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Clicks</CardDescription>
                        <CardTitle className="text-2xl">
                            {sponsors.reduce((sum, s) => sum + (s.click_count || 0), 0)}
                        </CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Sponsors List */}
            <Card>
                <CardHeader>
                    <CardTitle>All Sponsors</CardTitle>
                    <CardDescription>
                        Drag to reorder. Changes are saved automatically.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {sponsors.length === 0 ? (
                        <div className="text-center py-12 text-muted-foreground">
                            <ImageIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p>No sponsors yet</p>
                            <p className="text-sm mt-1">Add your first sponsor to get started</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {sponsors.map((sponsor) => (
                                <div
                                    key={sponsor.id}
                                    draggable
                                    onDragStart={(e) => handleDragStart(e, sponsor.id)}
                                    onDragOver={(e) => handleDragOver(e, sponsor.id)}
                                    onDragEnd={handleDragEnd}
                                    className={`
                                        flex items-center gap-4 p-3 rounded-lg border bg-card
                                        transition-all duration-150
                                        ${draggedId === sponsor.id ? 'opacity-50 scale-[0.98]' : ''}
                                        ${!sponsor.is_active ? 'opacity-60' : ''}
                                        hover:shadow-sm
                                    `}
                                >
                                    {/* Drag handle */}
                                    <div className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground">
                                        <GripVertical className="h-5 w-5" />
                                    </div>

                                    {/* Image preview */}
                                    <div className="w-20 h-12 rounded overflow-hidden bg-muted shrink-0 flex items-center justify-center">
                                        <img
                                            src={sponsor.image_url}
                                            alt={sponsor.name}
                                            className="w-full h-full object-contain"
                                            onError={(e) => {
                                                e.target.style.display = 'none'
                                            }}
                                        />
                                    </div>

                                    {/* Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium truncate">{sponsor.name}</span>
                                            {sponsor.is_active ? (
                                                <Badge variant="secondary" className="bg-emerald-50 text-emerald-700">
                                                    Active
                                                </Badge>
                                            ) : (
                                                <Badge variant="secondary" className="bg-secondary text-muted-foreground">
                                                    Inactive
                                                </Badge>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-3 text-sm text-muted-foreground mt-1">
                                            <span className="flex items-center gap-1 truncate max-w-[200px]">
                                                <ExternalLink className="h-3 w-3" />
                                                {sponsor.link_url}
                                            </span>
                                            <span className="flex items-center gap-1">
                                                <MousePointerClick className="h-3 w-3" />
                                                {sponsor.click_count || 0} clicks
                                            </span>
                                        </div>
                                    </div>

                                    {/* Actions */}
                                    <div className="flex items-center gap-2 shrink-0">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => handleToggleActive(sponsor)}
                                            title={sponsor.is_active ? 'Deactivate' : 'Activate'}
                                        >
                                            {sponsor.is_active ? (
                                                <Eye className="h-4 w-4" />
                                            ) : (
                                                <EyeOff className="h-4 w-4" />
                                            )}
                                        </Button>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => handleOpenEdit(sponsor)}
                                        >
                                            <Edit className="h-4 w-4" />
                                        </Button>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="text-destructive hover:text-destructive"
                                            onClick={() => setDeleteConfirmSponsor(sponsor)}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Preview Section */}
            {sponsors.filter(s => s.is_active).length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Preview</CardTitle>
                        <CardDescription>
                            How sponsors will appear in the sidebar
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="max-w-[256px] mx-auto">
                            <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
                                <div className="px-4 py-3 border-b bg-muted/30">
                                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                        Sponsors
                                    </h3>
                                </div>
                                <div className="p-3 space-y-3">
                                    {sponsors.filter(s => s.is_active).map((sponsor) => (
                                        <div
                                            key={sponsor.id}
                                            className="rounded-lg border bg-background p-2"
                                        >
                                            <div className="aspect-[16/9] w-full overflow-hidden rounded-md bg-muted flex items-center justify-center">
                                                <img
                                                    src={sponsor.image_url}
                                                    alt={sponsor.name}
                                                    className="w-full h-full object-contain"
                                                />
                                            </div>
                                            <p className="mt-2 text-xs text-center text-muted-foreground truncate">
                                                {sponsor.name}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Edit/Create Dialog */}
            <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
                <DialogContent className="sm:max-w-[500px]">
                    <DialogHeader>
                        <DialogTitle>
                            {editingSponsor ? 'Edit Sponsor' : 'Add Sponsor'}
                        </DialogTitle>
                        <DialogDescription>
                            {editingSponsor
                                ? 'Update the sponsor details below.'
                                : 'Add a new sponsor to display in the sidebar.'}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-4 py-4">
                        <div className="grid gap-2">
                            <Label htmlFor="name">Name *</Label>
                            <Input
                                id="name"
                                value={formData.name}
                                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                placeholder="e.g., Soccer.com"
                            />
                            {formErrors.name && (
                                <p className="text-sm text-destructive">{formErrors.name}</p>
                            )}
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="image_url">Image URL *</Label>
                            <Input
                                id="image_url"
                                value={formData.image_url}
                                onChange={(e) => setFormData(prev => ({ ...prev, image_url: e.target.value }))}
                                placeholder="https://example.com/logo.png"
                            />
                            {formErrors.image_url && (
                                <p className="text-sm text-destructive">{formErrors.image_url}</p>
                            )}
                            {formData.image_url && !formErrors.image_url && (
                                <div className="mt-2 p-2 border rounded-md bg-muted/50">
                                    <p className="text-xs text-muted-foreground mb-2">Preview:</p>
                                    <div className="aspect-[16/9] w-32 overflow-hidden rounded bg-card flex items-center justify-center">
                                        <img
                                            src={formData.image_url}
                                            alt="Preview"
                                            className="max-w-full max-h-full object-contain"
                                            onError={(e) => {
                                                e.target.parentElement.innerHTML = '<span class="text-xs text-destructive">Failed to load</span>'
                                            }}
                                        />
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="link_url">Link URL * (affiliate/sponsor link)</Label>
                            <Input
                                id="link_url"
                                value={formData.link_url}
                                onChange={(e) => setFormData(prev => ({ ...prev, link_url: e.target.value }))}
                                placeholder="https://example.com/?ref=yoursite"
                            />
                            {formErrors.link_url && (
                                <p className="text-sm text-destructive">{formErrors.link_url}</p>
                            )}
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="description">Description (tooltip)</Label>
                            <Textarea
                                id="description"
                                value={formData.description}
                                onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                                placeholder="Brief description shown on hover"
                                rows={2}
                            />
                        </div>

                        <div className="flex items-center gap-3">
                            <Switch
                                id="is_active"
                                checked={formData.is_active}
                                onCheckedChange={(checked) => setFormData(prev => ({ ...prev, is_active: checked }))}
                            />
                            <Label htmlFor="is_active" className="cursor-pointer">
                                Active (visible on site)
                            </Label>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleSave} disabled={saving}>
                            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {editingSponsor ? 'Save Changes' : 'Add Sponsor'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation */}
            <AlertDialog
                open={!!deleteConfirmSponsor}
                onOpenChange={(open) => !open && setDeleteConfirmSponsor(null)}
            >
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Sponsor</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete "{deleteConfirmSponsor?.name}"?
                            This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDelete}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                            {saving ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : null}
                            Delete
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}

export default AdminSponsors

