See the example interaction here are the things we need to fix

0. Multiple environmnetns
currently we have multiple envs. the nxd CLI can be pointed to any of them. As part of the setup we need to know what environment the user wants to use.
in customer this can be dev vs production. This was nicely done before by registering different meshes in this repo and having the user create / select the one. Can we do the same thing as part of this skill? /Users/sina/dev/nextdata/demo/mcp_tools/nxd_mcp
i.e. if there is no CLI env configuired ask what is the URL of the mesh and register it and if it is configuired with only one confirm that this is the only one you want to use for this session...and enable registering a new mesh as part of the setup, store it someone on the .nxd folder similar to /Users/sina/dev/nextdata/demo/mcp_tools/nxd_mcp so it is avialble for other sessions

1.I want to use https://github.com/nextdata-tech/nextdata-public-examples as an example reference for all these skills.


2. Infra selection
we need to know what services to use for inputs, transform and outputs. At the end of the set up we need a new skill to verify what compute and storage does the current person have access to. Look at the API auth in /Users/sina/dev/nextdata/nxd and docs in /Users/sina/dev/nextdata/nxd/docs. I THINK you can only launch the data product in domains that you have producer access to. so I feel before we start we need to ask which domain or have the user select infra profile that they have access to...but not sure what is the best way. Take a look at the




1. improvements around input discovery

When we bootstrap from data, the data product should be a source aligned data product
i.e. we won't try to change the shape of the data and we will keep it as is as much as possible.
each infra service shouild be 1 input
each file that has a unique schema should have its own input model
all the inputs should have input model expectations
and they should have model schema promises on the same model
sometimes the shape of the data is partioned based on time (days, months, years, etc.) this is a good indication of how scheduler should work. i.e. daily, hourly, etc. when data is partioned by time, there should always be an expecation & promise on data freshenss based on the timliness. If the data is NOT partioned the skill should ask the user  and confirm that data is not partioned and each run should replace the whole data or is this an incremental update.
currently the skill keep asking what is the goal of the DP. in case of bootstrap from data it is a soruce aligned DP.
currently the skill keep asking about the output but we have not got there yet. seems like our steps should be refactored so dependencies are met.
also seems like step 1 and 3 are overlapping now.


