          {selectedMatch && !hydrated ? (
            <Card><CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-sm text-muted-foreground">{hydrateError ? (<><InlineError>{hydrateError}</InlineError><Button variant="outline" onClick={() => setHydrateAttempt((n) => n + 1)}><RefreshCw className="mr-1.5 h-4 w-4" /> Retry</Button></>) : (<span className="inline-flex items-center"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading match details…</span>)}</CardContent></Card>
          ) : selectedMatch ? (
