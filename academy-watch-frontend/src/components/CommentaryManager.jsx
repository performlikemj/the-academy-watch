import { useState, useEffect } from 'react'
import { Button } from './ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs'
import { CommentaryEditor } from './CommentaryEditor'
import { Card, CardHeader, CardTitle, CardContent } from './ui/card'
import { Trash2, Edit2, Save, X, Plus } from 'lucide-react'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from './ui/alert-dialog'

export function CommentaryManager({ 
  newsletterId, 
  players = [],
  apiService,
  onCommentaryChange 
}) {
  const [commentaries, setCommentaries] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  
  // Editing state
  const [editingId, setEditingId] = useState(null)
  const [editingContent, setEditingContent] = useState('')
  
  // New commentary state
  const [showNewIntro, setShowNewIntro] = useState(false)
  const [showNewSummary, setShowNewSummary] = useState(false)
  const [newIntroContent, setNewIntroContent] = useState('')
  const [newSummaryContent, setNewSummaryContent] = useState('')
  const [showNewPlayerCommentary, setShowNewPlayerCommentary] = useState({})
  const [newPlayerContent, setNewPlayerContent] = useState({})
  
  // Delete confirmation
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  useEffect(() => {
    if (newsletterId) {
      loadCommentaries()
    }
  }, [newsletterId])

  const loadCommentaries = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiService.adminNewsletterCommentaryList(newsletterId)
      setCommentaries(data.commentaries || [])
      if (onCommentaryChange) onCommentaryChange(data.commentaries || [])
    } catch (err) {
      setError(err.message || 'Failed to load commentaries')
    } finally {
      setLoading(false)
    }
  }

  const createCommentary = async (type, content, playerId = null) => {
    setSaving(true)
    setError(null)
    try {
      await apiService.adminNewsletterCommentaryCreate(newsletterId, {
        commentary_type: type,
        content,
        player_id: playerId
      })
      
      await loadCommentaries()
      
      // Reset forms
      if (type === 'intro') {
        setShowNewIntro(false)
        setNewIntroContent('')
      } else if (type === 'summary') {
        setShowNewSummary(false)
        setNewSummaryContent('')
      } else if (type === 'player' && playerId) {
        setShowNewPlayerCommentary(prev => ({ ...prev, [playerId]: false }))
        setNewPlayerContent(prev => ({ ...prev, [playerId]: '' }))
      }
    } catch (err) {
      setError(err.message || 'Failed to create commentary')
    } finally {
      setSaving(false)
    }
  }

  const updateCommentary = async (commentaryId, content) => {
    setSaving(true)
    setError(null)
    try {
      await apiService.adminNewsletterCommentaryUpdate(commentaryId, { content })
      
      await loadCommentaries()
      setEditingId(null)
      setEditingContent('')
    } catch (err) {
      setError(err.message || 'Failed to update commentary')
    } finally {
      setSaving(false)
    }
  }

  const deleteCommentary = async (commentaryId) => {
    setSaving(true)
    setError(null)
    try {
      await apiService.adminNewsletterCommentaryDelete(commentaryId)
      
      await loadCommentaries()
      setDeleteConfirm(null)
    } catch (err) {
      setError(err.message || 'Failed to delete commentary')
    } finally {
      setSaving(false)
    }
  }

  const getCommentaryForType = (type, playerId = null) => {
    return commentaries.filter(c => {
      if (type === 'player') {
        return c.commentary_type === 'player' && c.player_id === playerId
      }
      return c.commentary_type === type
    })
  }

  const startEditing = (commentary) => {
    setEditingId(commentary.id)
    setEditingContent(commentary.content)
  }

  const cancelEditing = () => {
    setEditingId(null)
    setEditingContent('')
  }

  if (loading) {
    return <div className="text-center py-8">Loading commentaries...</div>
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 p-3 rounded-md">
          {error}
        </div>
      )}

      <Tabs defaultValue="intro" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="intro">Introduction</TabsTrigger>
          <TabsTrigger value="players">Player Commentary</TabsTrigger>
          <TabsTrigger value="summary">Summary</TabsTrigger>
        </TabsList>

        {/* Introduction Tab */}
        <TabsContent value="intro" className="space-y-4">
          {getCommentaryForType('intro').map(commentary => (
            <Card key={commentary.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Introduction Commentary</CardTitle>
                  <div className="flex gap-2">
                    {editingId === commentary.id ? (
                      <>
                        <Button 
                          size="sm" 
                          onClick={() => updateCommentary(commentary.id, editingContent)}
                          disabled={saving}
                        >
                          <Save className="h-4 w-4 mr-1" /> Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={cancelEditing}>
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => startEditing(commentary)}>
                          <Edit2 className="h-4 w-4" />
                        </Button>
                        <Button 
                          size="sm" 
                          variant="ghost" 
                          onClick={() => setDeleteConfirm(commentary.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">By {commentary.author_name}</p>
              </CardHeader>
              <CardContent>
                {editingId === commentary.id ? (
                  <CommentaryEditor 
                    value={editingContent}
                    onChange={setEditingContent}
                  />
                ) : (
                  <div 
                    className="prose prose-sm dark:prose-invert max-w-none"
                    dangerouslySetInnerHTML={{ __html: commentary.content }}
                  />
                )}
              </CardContent>
            </Card>
          ))}

          {!showNewIntro && getCommentaryForType('intro').length === 0 && (
            <Button onClick={() => setShowNewIntro(true)}>
              <Plus className="h-4 w-4 mr-2" /> Add Introduction Commentary
            </Button>
          )}

          {showNewIntro && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">New Introduction Commentary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <CommentaryEditor 
                  value={newIntroContent}
                  onChange={setNewIntroContent}
                  placeholder="Write an introduction for the newsletter..."
                />
                <div className="flex gap-2">
                  <Button 
                    onClick={() => createCommentary('intro', newIntroContent)}
                    disabled={!newIntroContent.trim() || saving}
                  >
                    <Save className="h-4 w-4 mr-1" /> Save
                  </Button>
                  <Button variant="ghost" onClick={() => setShowNewIntro(false)}>
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Players Tab */}
        <TabsContent value="players" className="space-y-4">
          {players.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No players found in newsletter
            </p>
          ) : (
            players.map(player => {
              const playerCommentaries = getCommentaryForType('player', player.id)
              const isShowingNew = showNewPlayerCommentary[player.id]
              
              return (
                <Card key={player.id}>
                  <CardHeader>
                    <CardTitle className="text-sm">
                      {player.name} ({player.team})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {playerCommentaries.map(commentary => (
                      <div key={commentary.id} className="border rounded-lg p-3">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-xs text-muted-foreground">By {commentary.author_name}</p>
                          <div className="flex gap-2">
                            {editingId === commentary.id ? (
                              <>
                                <Button 
                                  size="sm" 
                                  onClick={() => updateCommentary(commentary.id, editingContent)}
                                  disabled={saving}
                                >
                                  <Save className="h-4 w-4 mr-1" /> Save
                                </Button>
                                <Button size="sm" variant="ghost" onClick={cancelEditing}>
                                  <X className="h-4 w-4" />
                                </Button>
                              </>
                            ) : (
                              <>
                                <Button size="sm" variant="ghost" onClick={() => startEditing(commentary)}>
                                  <Edit2 className="h-4 w-4" />
                                </Button>
                                <Button 
                                  size="sm" 
                                  variant="ghost" 
                                  onClick={() => setDeleteConfirm(commentary.id)}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </>
                            )}
                          </div>
                        </div>
                        {editingId === commentary.id ? (
                          <CommentaryEditor 
                            value={editingContent}
                            onChange={setEditingContent}
                          />
                        ) : (
                          <div 
                            className="prose prose-sm dark:prose-invert max-w-none"
                            dangerouslySetInnerHTML={{ __html: commentary.content }}
                          />
                        )}
                      </div>
                    ))}

                    {!isShowingNew && (
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={() => setShowNewPlayerCommentary(prev => ({ ...prev, [player.id]: true }))}
                      >
                        <Plus className="h-4 w-4 mr-2" /> Add Commentary
                      </Button>
                    )}

                    {isShowingNew && (
                      <div className="space-y-2">
                        <CommentaryEditor 
                          value={newPlayerContent[player.id] || ''}
                          onChange={(content) => setNewPlayerContent(prev => ({ ...prev, [player.id]: content }))}
                          placeholder={`Write commentary about ${player.name}...`}
                        />
                        <div className="flex gap-2">
                          <Button 
                            size="sm"
                            onClick={() => createCommentary('player', newPlayerContent[player.id], player.id)}
                            disabled={!newPlayerContent[player.id]?.trim() || saving}
                          >
                            <Save className="h-4 w-4 mr-1" /> Save
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost" 
                            onClick={() => setShowNewPlayerCommentary(prev => ({ ...prev, [player.id]: false }))}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )
            })
          )}
        </TabsContent>

        {/* Summary Tab */}
        <TabsContent value="summary" className="space-y-4">
          {getCommentaryForType('summary').map(commentary => (
            <Card key={commentary.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Summary Commentary</CardTitle>
                  <div className="flex gap-2">
                    {editingId === commentary.id ? (
                      <>
                        <Button 
                          size="sm" 
                          onClick={() => updateCommentary(commentary.id, editingContent)}
                          disabled={saving}
                        >
                          <Save className="h-4 w-4 mr-1" /> Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={cancelEditing}>
                          <X className="h-4 w-4" />
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => startEditing(commentary)}>
                          <Edit2 className="h-4 w-4" />
                        </Button>
                        <Button 
                          size="sm" 
                          variant="ghost" 
                          onClick={() => setDeleteConfirm(commentary.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">By {commentary.author_name}</p>
              </CardHeader>
              <CardContent>
                {editingId === commentary.id ? (
                  <CommentaryEditor 
                    value={editingContent}
                    onChange={setEditingContent}
                  />
                ) : (
                  <div 
                    className="prose prose-sm dark:prose-invert max-w-none"
                    dangerouslySetInnerHTML={{ __html: commentary.content }}
                  />
                )}
              </CardContent>
            </Card>
          ))}

          {!showNewSummary && getCommentaryForType('summary').length === 0 && (
            <Button onClick={() => setShowNewSummary(true)}>
              <Plus className="h-4 w-4 mr-2" /> Add Summary Commentary
            </Button>
          )}

          {showNewSummary && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">New Summary Commentary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <CommentaryEditor 
                  value={newSummaryContent}
                  onChange={setNewSummaryContent}
                  placeholder="Write a summary for the newsletter..."
                />
                <div className="flex gap-2">
                  <Button 
                    onClick={() => createCommentary('summary', newSummaryContent)}
                    disabled={!newSummaryContent.trim() || saving}
                  >
                    <Save className="h-4 w-4 mr-1" /> Save
                  </Button>
                  <Button variant="ghost" onClick={() => setShowNewSummary(false)}>
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Commentary</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this commentary? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={() => deleteCommentary(deleteConfirm)}
              disabled={saving}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

