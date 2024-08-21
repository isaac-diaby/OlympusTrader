import streamlit as st

def strategy_select():
    import glob
    strategies = glob.glob("*.py")
    selected_strategy = st.selectbox("Select a strategy", strategies)
    
    view_col, run_col = st.columns(2) 
    output_container = st.container()
    with view_col:
        if st.button("View Strategy"):
            st.write(f"Viewing {selected_strategy}")
            with output_container:
                with open(selected_strategy, "r") as f:
                    st.code(f.read(), language="python")
    with run_col:
        if st.button("Run Strategy backtest (Not yet supported)"):
            st.error("Running strategies is not yet supported")
            # st.warning(f"Running {selected_strategy}")
            # import subprocess
            # NotImplementedError("Running strategies is not yet supported")
    
            # runner: subprocess.CompletedProcess = subprocess.run(["python", selected_strategy], stdout=subprocess.PIPE) 
            # # runner: subprocess.CompletedProcess = subprocess.run(["python", selected_strategy], stdout=subprocess.PIPE) 
            # output = runner.stdout
            # st.write(f"Process exited with code {runner.returncode}")
            # with output_container:
            #     st.write(output)

            # st.stop()
        
strategy_select()