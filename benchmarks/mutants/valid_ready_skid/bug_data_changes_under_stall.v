module top_module(
    input logic clk,
    input logic reset,
    input logic in_valid,
    input logic [7:0] in_data,
    output logic in_ready,
    output logic out_valid,
    output logic [7:0] out_data,
    input logic out_ready
);
    logic full;

    assign in_ready = !full || out_ready;
    assign out_valid = full ? 1'b1 : in_valid;
    assign out_data = full ? in_data : in_data;

    always_ff @(posedge clk) begin
        if (reset) begin
            full <= 1'b0;
        end else if (in_valid && in_ready && !out_ready) begin
            full <= 1'b1;
        end else if (out_ready) begin
            full <= 1'b0;
        end
    end
endmodule
