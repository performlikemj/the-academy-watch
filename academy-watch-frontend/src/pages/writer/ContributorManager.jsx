import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter
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
import { Loader2, Plus, Edit, Trash2, ArrowLeft, Users, ExternalLink } from 'lucide-react'
import { APIService } from '@/lib/api'

export function ContributorManager() {
    const navigate = useNavigate()
    const [loading, setLoading] = useState(true)
    const [contributors, setContributors] = useState([])
    const [error, setError] = useState('')

    // Dialog states
    const [dialogOpen, setDialogOpen] = useState(false)
    const [editingContributor, setEditingContributor] = useState(null)
    const [saving, setSaving] = useState(false)

    // Form state
    const [formData, setFormData] = useState({
        name: '',
        bio: '',
        photo_url: '',
        attribution_url: '',
        attribution_name: ''
    })
    const [formError, setFormError] = useState('')

    // Delete state
    const [deletingId, setDeletingId] = useState(null)
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

    const loadContributors = async () => {
        try {
            setLoading(true)
            const data = await APIService.getWriterContributors()
            setContributors(data || [])
        } catch (err) {
            console.error('Failed to load contributors', err)
            setError('Failed to load contributors. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        loadContributors()
    }, [])

    const resetForm = () => {
        setFormData({
            name: '',
            bio: '',
            photo_url: '',
            attribution_url: '',
            attribution_name: ''
        })
        setFormError('')
        setEditingContributor(null)
    }

    const openAddDialog = () => {
        resetForm()
        setDialogOpen(true)
    }

    const openEditDialog = (contributor) => {
        setEditingContributor(contributor)
        setFormData({
            name: contributor.name || '',
            bio: contributor.bio || '',
            photo_url: contributor.photo_url || '',
            attribution_url: contributor.attribution_url || '',
            attribution_name: contributor.attribution_name || ''
        })
        setFormError('')
        setDialogOpen(true)
    }

    const handleSave = async () => {
        // Validate
        if (!formData.name.trim()) {
            setFormError('Name is required')
            return
        }

        if (formData.photo_url && !formData.photo_url.startsWith('http://') && !formData.photo_url.startsWith('https://')) {
            setFormError('Photo URL must start with http:// or https://')
            return
        }

        if (formData.attribution_url && !formData.attribution_url.startsWith('http://') && !formData.attribution_url.startsWith('https://')) {
            setFormError('Attribution URL must start with http:// or https://')
            return
        }

        try {
            setSaving(true)
            setFormError('')

            const payload = {
                name: formData.name.trim(),
                bio: formData.bio.trim() || null,
                photo_url: formData.photo_url.trim() || null,
                attribution_url: formData.attribution_url.trim() || null,
                attribution_name: formData.attribution_name.trim() || null
            }

            if (editingContributor) {
                await APIService.updateContributor(editingContributor.id, payload)
            } else {
                await APIService.createContributor(payload)
            }

            setDialogOpen(false)
            resetForm()
            loadContributors()
        } catch (err) {
            console.error('Failed to save contributor', err)
            setFormError(err.message || 'Failed to save contributor')
        } finally {
            setSaving(false)
        }
    }

    const confirmDelete = (id) => {
        setDeletingId(id)
        setShowDeleteConfirm(true)
    }

    const handleDelete = async () => {
        if (!deletingId) return

        try {
            await APIService.deleteContributor(deletingId)
            setContributors(prev => prev.filter(c => c.id !== deletingId))
        } catch (err) {
            console.error('Failed to delete contributor', err)
            setError('Failed to delete contributor')
        } finally {
            setDeletingId(null)
            setShowDeleteConfirm(false)
        }
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
            {/* Header */}
            <div className="bg-card border-b">
                <div className="max-w-4xl mx-auto px-4 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => navigate('/writer')}
                            >
                                <ArrowLeft className="h-4 w-4 mr-2" />
                                Back
                            </Button>
                            <div>
                                <h1 className="text-xl font-semibold">Contributors</h1>
                                <p className="text-sm text-muted-foreground">
                                    Manage profiles for scouts and guest contributors
                                </p>
                            </div>
                        </div>
                        <Button onClick={openAddDialog}>
                            <Plus className="h-4 w-4 mr-2" />
                            Add Contributor
                        </Button>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-4xl mx-auto px-4 py-6">
                {error && (
                    <div className="bg-rose-50 text-rose-600 p-4 rounded-lg mb-6">
                        {error}
                    </div>
                )}

                {contributors.length === 0 ? (
                    <Card>
                        <CardContent className="py-12">
                            <div className="text-center">
                                <Users className="h-12 w-12 text-muted-foreground/70 mx-auto mb-4" />
                                <h3 className="text-lg font-medium text-foreground mb-2">
                                    No contributors yet
                                </h3>
                                <p className="text-muted-foreground mb-6">
                                    Create profiles for scouts and guest analysts who contribute content.
                                </p>
                                <Button onClick={openAddDialog}>
                                    <Plus className="h-4 w-4 mr-2" />
                                    Add Your First Contributor
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-4">
                        {contributors.map((contributor) => (
                            <Card key={contributor.id}>
                                <CardContent className="py-4">
                                    <div className="flex items-start gap-4">
                                        <Avatar className="h-14 w-14">
                                            {contributor.photo_url ? (
                                                <AvatarImage src={contributor.photo_url} alt={contributor.name} />
                                            ) : null}
                                            <AvatarFallback className="text-lg bg-primary/10 text-primary">
                                                {(contributor.name || 'C').substring(0, 2).toUpperCase()}
                                            </AvatarFallback>
                                        </Avatar>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <h3 className="font-semibold text-foreground">
                                                    {contributor.name}
                                                </h3>
                                                {contributor.attribution_url && (
                                                    <a
                                                        href={contributor.attribution_url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-primary hover:text-primary/80 flex items-center gap-1 text-sm"
                                                    >
                                                        {contributor.attribution_name || 'Website'}
                                                        <ExternalLink className="h-3 w-3" />
                                                    </a>
                                                )}
                                            </div>
                                            {contributor.bio && (
                                                <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                                                    {contributor.bio}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => openEditDialog(contributor)}
                                            >
                                                <Edit className="h-4 w-4" />
                                            </Button>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                                                onClick={() => confirmDelete(contributor.id)}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}
            </div>

            {/* Add/Edit Dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle>
                            {editingContributor ? 'Edit Contributor' : 'Add Contributor'}
                        </DialogTitle>
                        <DialogDescription>
                            {editingContributor
                                ? 'Update the contributor profile details.'
                                : 'Create a profile for a scout or guest contributor.'}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        {formError && (
                            <div className="bg-rose-50 text-rose-600 p-3 rounded-lg text-sm">
                                {formError}
                            </div>
                        )}

                        <div className="space-y-2">
                            <Label htmlFor="name">Name *</Label>
                            <Input
                                id="name"
                                value={formData.name}
                                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                placeholder="Scout name or organization"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="bio">Bio</Label>
                            <Textarea
                                id="bio"
                                value={formData.bio}
                                onChange={(e) => setFormData(prev => ({ ...prev, bio: e.target.value }))}
                                placeholder="Brief description or credentials"
                                rows={3}
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="photo_url">Photo/Logo URL</Label>
                            <Input
                                id="photo_url"
                                value={formData.photo_url}
                                onChange={(e) => setFormData(prev => ({ ...prev, photo_url: e.target.value }))}
                                placeholder="https://example.com/photo.jpg"
                            />
                            <p className="text-xs text-muted-foreground">
                                URL to a photo or logo image
                            </p>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="attribution_url">Website URL</Label>
                            <Input
                                id="attribution_url"
                                value={formData.attribution_url}
                                onChange={(e) => setFormData(prev => ({ ...prev, attribution_url: e.target.value }))}
                                placeholder="https://example.com"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="attribution_name">Website Label</Label>
                            <Input
                                id="attribution_name"
                                value={formData.attribution_name}
                                onChange={(e) => setFormData(prev => ({ ...prev, attribution_name: e.target.value }))}
                                placeholder="Visit Website"
                            />
                            <p className="text-xs text-muted-foreground">
                                Text displayed for the website link
                            </p>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleSave} disabled={saving}>
                            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            {editingContributor ? 'Save Changes' : 'Add Contributor'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation */}
            <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Contributor</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this contributor? This action cannot be undone.
                            Existing content attributed to this contributor will keep the attribution text but lose the link.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDelete}
                            className="bg-rose-600 hover:bg-rose-700"
                        >
                            Delete
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}
