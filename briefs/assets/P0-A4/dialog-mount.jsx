        <IntroduceDialog
          open={!!introducePlayer}
          onOpenChange={(next) => { if (!next) setIntroducePlayer(null) }}
          player={introducePlayer}
        />
