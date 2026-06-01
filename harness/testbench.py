from __future__ import annotations

from harness.task_schema import HDLTask


def _comb_truth_table(task: HDLTask) -> str:
    ids = task.id
    if ids == "local_comb_and_gate":
        return """
module tb;
  reg a, b; wire y;
  top_module dut(.a(a), .b(b), .y(y));
  initial begin
    for (integer i = 0; i < 4; i = i + 1) begin
      {a,b} = i[1:0]; #1;
      if (y !== (a & b)) $fatal(1, "and mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    if ids == "local_comb_mux2":
        return """
module tb;
  reg a, b, sel; wire y;
  top_module dut(.a(a), .b(b), .sel(sel), .y(y));
  initial begin
    for (integer i = 0; i < 8; i = i + 1) begin
      {sel,a,b} = i[2:0]; #1;
      if (y !== (sel ? b : a)) $fatal(1, "mux mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    if ids == "local_arith_half_adder":
        return """
module tb;
  reg a, b; wire sum, cout;
  top_module dut(.a(a), .b(b), .sum(sum), .cout(cout));
  initial begin
    for (integer i = 0; i < 4; i = i + 1) begin
      {a,b} = i[1:0]; #1;
      if ({cout,sum} !== (a + b)) $fatal(1, "half adder mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    if ids == "local_arith_full_adder":
        return """
module tb;
  reg a, b, cin; wire sum, cout;
  top_module dut(.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));
  initial begin
    for (integer i = 0; i < 8; i = i + 1) begin
      {a,b,cin} = i[2:0]; #1;
      if ({cout,sum} !== (a + b + cin)) $fatal(1, "full adder mismatch");
    end
    $display("PASS");
  end
endmodule
"""
    raise ValueError(f"No truth-table generator for {task.id}")


def generate_testbench(task: HDLTask) -> str:
    def with_timescale(body: str) -> str:
        return "`timescale 1ns/1ps\n" + body.lstrip()

    if task.expected.type == "truth_table":
        return with_timescale(_comb_truth_table(task))
    if task.id == "local_vector_reverse8":
        return with_timescale("""
module tb;
  reg [7:0] in; wire [7:0] out;
  top_module dut(.in(in), .out(out));
  function [7:0] rev(input [7:0] x);
    integer j;
    begin
      for (j = 0; j < 8; j = j + 1) rev[j] = x[7-j];
    end
  endfunction
  initial begin
    for (integer i = 0; i < 256; i = i + 1) begin
      in = i[7:0]; #1;
      if (out !== rev(in)) $fatal(1, "reverse mismatch");
    end
    $display("PASS");
  end
endmodule
""")
    if task.id == "local_popcount4":
        return with_timescale("""
module tb;
  reg [3:0] in; wire [2:0] count;
  top_module dut(.in(in), .count(count));
  function [2:0] pc(input [3:0] x);
    begin pc = x[0] + x[1] + x[2] + x[3]; end
  endfunction
  initial begin
    for (integer i = 0; i < 16; i = i + 1) begin
      in = i[3:0]; #1;
      if (count !== pc(in)) $fatal(1, "popcount mismatch");
    end
    $display("PASS");
  end
endmodule
""")
    if task.id == "local_priority_encoder4":
        return with_timescale("""
module tb;
  reg [3:0] in; wire [1:0] pos; wire valid;
  top_module dut(.in(in), .pos(pos), .valid(valid));
  reg [1:0] exp_pos; reg exp_valid;
  initial begin
    for (integer i = 0; i < 16; i = i + 1) begin
      in = i[3:0]; #1;
      exp_valid = |in;
      if (in[3]) exp_pos = 2'd3;
      else if (in[2]) exp_pos = 2'd2;
      else if (in[1]) exp_pos = 2'd1;
      else exp_pos = 2'd0;
      if (valid !== exp_valid || pos !== exp_pos) $fatal(1, "priority mismatch");
    end
    $display("PASS");
  end
endmodule
""")
    if task.id == "local_dff_sync_reset":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, d=0; wire q;
  top_module dut(.clk(clk), .reset(reset), .d(d), .q(q));
  always #1 clk = ~clk;
  initial begin
    reset=1; d=1; @(posedge clk); #0.1; if (q !== 0) $fatal(1, "reset failed");
    reset=0; d=1; @(posedge clk); #0.1; if (q !== 1) $fatal(1, "capture 1 failed");
    d=0; @(posedge clk); #0.1; if (q !== 0) $fatal(1, "capture 0 failed");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_counter_mod10":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, enable=0; wire [3:0] count;
  top_module dut(.clk(clk), .reset(reset), .enable(enable), .count(count));
  always #1 clk = ~clk;
  integer exp;
  initial begin
    reset=1; enable=1; exp=0; @(posedge clk); #0.1; if (count !== 0) $fatal(1, "reset failed");
    reset=0;
    for (integer i=0; i<25; i=i+1) begin
      @(posedge clk); exp = (exp == 9) ? 0 : exp + 1; #0.1;
      if (count !== exp[3:0]) $fatal(1, "counter mismatch");
    end
    enable=0; @(posedge clk); #0.1; if (count !== exp[3:0]) $fatal(1, "hold failed");
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_edge_detect_rise":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, sig=0; wire rise;
  top_module dut(.clk(clk), .reset(reset), .sig(sig), .rise(rise));
  always #1 clk = ~clk;
  task step(input v, input exp);
    begin sig=v; @(posedge clk); #0.1; if (rise !== exp) $fatal(1, "rise mismatch"); end
  endtask
  initial begin
    reset=1; step(0,0); reset=0;
    step(0,0); step(1,1); step(1,0); step(0,0); step(1,1);
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_fsm_101_detector":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, bit_in=0; wire found;
  top_module dut(.clk(clk), .reset(reset), .bit_in(bit_in), .found(found));
  always #1 clk = ~clk;
  reg [31:0] hist;
  task step(input b);
    reg exp;
    begin
      bit_in=b; @(posedge clk); hist = {hist[30:0], b}; #0.1;
      exp = (hist[2:0] == 3'b101);
      if (found !== exp) $fatal(1, "fsm mismatch");
    end
  endtask
  initial begin
    hist=0; reset=1; step(0); reset=0;
    step(1); step(0); step(1); step(0); step(1); step(1); step(0); step(1);
    $display("PASS"); $finish;
  end
endmodule
""")
    if task.id == "local_valid_ready_skid":
        return with_timescale("""
module tb;
  reg clk=0, reset=0, in_valid=0, out_ready=0; reg [7:0] in_data=0;
  wire in_ready, out_valid; wire [7:0] out_data;
  top_module dut(.clk(clk), .reset(reset), .in_valid(in_valid), .in_data(in_data),
                 .in_ready(in_ready), .out_valid(out_valid), .out_data(out_data),
                 .out_ready(out_ready));
  always #1 clk = ~clk;
  initial begin
    reset=1; @(posedge clk); #0.1; reset=0;
    in_valid=1; in_data=8'h3c; out_ready=0; @(posedge clk); #0.1;
    if (!out_valid || out_data !== 8'h3c) $fatal(1, "did not present data");
    in_valid=0; in_data=8'ha5; repeat (3) begin @(posedge clk); #0.1;
      if (!out_valid || out_data !== 8'h3c) $fatal(1, "data not stable under backpressure");
    end
    out_ready=1; @(posedge clk); #0.1;
    $display("PASS"); $finish;
  end
endmodule
""")
    raise ValueError(f"No testbench generator for {task.id}")
